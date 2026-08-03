<?php

class Database {
    private $dataDir;
    private $usersFile;
    private $keysFile;
    private $hitsFile;
    private $settingsFile;
    private $binLibraryFile;
    private $hitCountsFile;

    /** Keeps one open lock-handle per file path for the lifetime of a request */
    private $lockHandles = [];

    public function __construct($dataDir) {
        $this->dataDir = rtrim($dataDir, '/');
        $this->usersFile       = $this->dataDir . '/users.json';
        $this->keysFile        = $this->dataDir . '/license_keys.json';
        $this->hitsFile        = $this->dataDir . '/hits.json';
        $this->settingsFile    = $this->dataDir . '/settings.json';
        $this->binLibraryFile  = $this->dataDir . '/bin_library.json';
        $this->hitCountsFile   = $this->dataDir . '/hit_counts.json';

        if (!is_dir($this->dataDir)) {
            mkdir($this->dataDir, 0755, true);
            @chmod($this->dataDir, 0755);
        }

        $this->initFiles();
    }

    public function __destruct() {
        foreach ($this->lockHandles as $path => $fp) {
            if (is_resource($fp)) {
                flock($fp, LOCK_UN);
                fclose($fp);
            }
        }
        $this->lockHandles = [];
    }

    /* ─── Initialisation ─── */

    private function initFiles() {
        $defaults = [
            $this->usersFile      => [],
            $this->keysFile       => [],
            $this->hitsFile       => [],
            $this->settingsFile   => [
                'telegram_channel' => 'https://t.me/stripebinssss',
                'latest_version'  => '1.0.7'
            ],
            $this->binLibraryFile => [],
            $this->hitCountsFile  => ['global' => ['total_hits' => 0], 'users' => []]
        ];

        foreach ($defaults as $file => $content) {
            if (!file_exists($file)) {
                $this->atomicWrite($file, $content);
                @chmod($file, 0644);
            }
        }
    }

    /* ─── Low-level I/O with proper locking ─── */

    /**
     * Acquire an exclusive lock file for the given data file.
     * Returns the lock file-handle so the caller can release it.
     */
    private function acquireLock(string $file, int $mode = LOCK_EX) {
        $lockPath = $file . '.lock';

        if (!isset($this->lockHandles[$lockPath]) || !is_resource($this->lockHandles[$lockPath])) {
            $fp = @fopen($lockPath, 'c');
            if (!$fp) {
                error_log("[Database] Cannot open lock file: $lockPath");
                return false;
            }
            $this->lockHandles[$lockPath] = $fp;
        }

        $fp = $this->lockHandles[$lockPath];

        $tries = 0;
        while (!flock($fp, $mode | LOCK_NB)) {
            if (++$tries > 100) {               // ~5 s total
                error_log("[Database] Lock timeout on $lockPath");
                return false;
            }
            usleep(50000);                       // 50 ms
        }

        return $fp;
    }

    private function releaseLock(string $file) {
        $lockPath = $file . '.lock';
        if (isset($this->lockHandles[$lockPath]) && is_resource($this->lockHandles[$lockPath])) {
            flock($this->lockHandles[$lockPath], LOCK_UN);
        }
    }

    /**
     * Read JSON with a shared lock (non-blocking to readers).
     */
    private function readJson(string $file): array {
        if (!file_exists($file)) {
            return [];
        }

        $lockFp = $this->acquireLock($file, LOCK_SH);
        $content = @file_get_contents($file);
        if ($lockFp) {
            $this->releaseLock($file);
        }

        if ($content === false || $content === '') {
            return [];
        }

        $data = json_decode($content, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            error_log("[Database] JSON decode error in $file: " . json_last_error_msg());
            return [];
        }

        return is_array($data) ? $data : [];
    }

    /**
     * Atomic write: temp file -> fsync -> rename (prevents corruption
     * if two processes write concurrently).
     */
    private function atomicWrite(string $file, $data): bool {
        $dir = dirname($file);
        if (!is_dir($dir)) {
            @mkdir($dir, 0755, true);
        }

        $json = json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
        if ($json === false) {
            error_log("[Database] JSON encode error: " . json_last_error_msg());
            return false;
        }

        $tmp = $file . '.tmp.' . getmypid() . '.' . mt_rand(1000, 9999);
        $fp  = @fopen($tmp, 'w');
        if (!$fp) {
            error_log("[Database] Cannot create temp file: $tmp");
            return false;
        }

        $ok = fwrite($fp, $json);
        fflush($fp);
        fclose($fp);

        if ($ok === false) {
            @unlink($tmp);
            return false;
        }

        if (!@rename($tmp, $file)) {
            @copy($tmp, $file);
            @unlink($tmp);
        }

        @chmod($file, 0644);
        return true;
    }

    /**
     * Read-modify-write under an exclusive lock so concurrent requests
     * never overwrite each other's changes.
     */
    private function lockedUpdate(string $file, callable $mutator) {
        $lockFp = $this->acquireLock($file, LOCK_EX);

        // Re-read inside the lock to get the freshest state
        $content = @file_get_contents($file);
        $data = ($content !== false && $content !== '')
            ? (json_decode($content, true) ?? [])
            : [];

        $result = $mutator($data);

        $this->atomicWrite($file, $data);

        if ($lockFp) {
            $this->releaseLock($file);
        }

        return $result;
    }

    /* ─── Users ─── */

    public function getUser($userId) {
        $users = $this->readJson($this->usersFile);
        $needle = (string)$userId;
        foreach ($users as $user) {
            if ((string)($user['user_id'] ?? '') === $needle) {
                return $user;
            }
        }
        return null;
    }

    public function getUserByToken($token) {
        if (!$token || strlen($token) !== 15) {
            return null;
        }
        $users = $this->readJson($this->usersFile);
        foreach ($users as $user) {
            if (isset($user['token']) && $user['token'] === $token) {
                return $user;
            }
        }
        return null;
    }

    public function isTokenExists($token): bool {
        return $this->getUserByToken($token) !== null;
    }

    public function createUser(array $data) {
        $needle = (string)$data['user_id'];

        return $this->lockedUpdate($this->usersFile, function (&$users) use ($data, $needle) {
            // Double-check inside the lock
            foreach ($users as $u) {
                if ((string)($u['user_id'] ?? '') === $needle) {
                    return $u;
                }
            }
            $user = [
                'user_id'    => $needle,
                'username'   => $data['username'] ?? '',
                'first_name' => $data['first_name'] ?? '',
                'token'      => null,
                'hits'       => 0,
                'attempts'   => 0,
                'banned'     => false,
                'created_at' => date('c'),
                'last_active'=> date('c')
            ];
            $users[] = $user;
            return $user;
        });
    }

    public function updateUser($userId, array $updates): bool {
        $needle = (string)$userId;

        return $this->lockedUpdate($this->usersFile, function (&$users) use ($needle, $updates) {
            foreach ($users as &$user) {
                if ((string)($user['user_id'] ?? '') === $needle) {
                    foreach ($updates as $k => $v) {
                        $user[$k] = $v;
                    }
                    $user['last_active'] = date('c');
                    return true;
                }
            }
            return false;
        });
    }

    public function incrementStat($userId, string $stat): int {
        $needle = (string)$userId;

        $newVal = $this->lockedUpdate($this->usersFile, function (&$users) use ($needle, $stat) {
            foreach ($users as &$user) {
                if ((string)($user['user_id'] ?? '') === $needle) {
                    $old = isset($user[$stat]) ? (int)$user[$stat] : 0;
                    $user[$stat] = $old + 1;
                    $user['last_active'] = date('c');
                    return $user[$stat];
                }
            }
            return 0;
        });

        // Atomically update BOTH global and user hit counts in one locked write
        if ($stat === 'hits' && $newVal > 0) {
            $this->incrementHitCounts($needle);
        }

        return $newVal;
    }

    public function getUserBins($userId): array {
        return [];
    }

    public function getTopUsers(int $limit = 10): array {
        $users = $this->readJson($this->usersFile);
        usort($users, function ($a, $b) {
            return ($b['hits'] ?? 0) - ($a['hits'] ?? 0);
        });
        return array_slice($users, 0, $limit);
    }

    /**
     * Get the rank of a specific user among all users, sorted by hits descending.
     * Returns ['rank' => int, 'hits' => int, 'first_name' => string, 'username' => string] or null.
     */
    public function getUserRank($userId): ?array {
        $users = $this->readJson($this->usersFile);
        usort($users, function ($a, $b) {
            return ($b['hits'] ?? 0) - ($a['hits'] ?? 0);
        });
        $needle = (string)$userId;
        foreach ($users as $i => $u) {
            if ((string)($u['user_id'] ?? '') === $needle) {
                return [
                    'rank'       => $i + 1,
                    'user_id'    => $needle,
                    'first_name' => $u['first_name'] ?? '',
                    'username'   => $u['username'] ?? '',
                    'pfp_url'    => $u['pfp_url'] ?? '',
                    'hits'       => (int)($u['hits'] ?? 0),
                    'total_users'=> count($users)
                ];
            }
        }
        return null;
    }

    public function getAllUsers(): array {
        return $this->readJson($this->usersFile);
    }

    public function getAllHits(): array {
        return $this->readJson($this->hitsFile);
    }

    public function getGlobalStats(): array {
        $users = $this->readJson($this->usersFile);
        $totalHits = 0;
        $totalAttempts = 0;
        foreach ($users as $u) {
            $totalHits     += (int)($u['hits'] ?? 0);
            $totalAttempts += (int)($u['attempts'] ?? 0);
        }
        return [
            'total_users'    => count($users),
            'total_hits'     => $totalHits,
            'total_attempts' => $totalAttempts
        ];
    }

    /* ─── Hit Counters (unified hit_counts.json) ─── */
    /*
     * Structure of hit_counts.json:
     * {
     *   "global": { "total_hits": N },
     *   "users": {
     *     "<user_id>": N,
     *     "<user_id>": N
     *   }
     * }
     *
     * Both global and per-user counters live in ONE file so they are
     * always updated together in a single lockedUpdate() call -- no
     * more race conditions between separate global.json / user_hits.json.
     */

    /**
     * Ensure hit_counts.json has correct structure (handles migration
     * from old global.json / user_hits.json format).
     */
    private function ensureHitCountsStructure(array &$data): void {
        if (!isset($data['global']) || !is_array($data['global'])) {
            $data['global'] = ['total_hits' => 0];
        }
        if (!isset($data['users']) || !is_array($data['users'])) {
            $data['users'] = [];
        }
    }

    /**
     * Auto-migrate old global.json + user_hits.json into hit_counts.json
     * if the old files exist and hit_counts.json is empty/new.
     */
    public function migrateOldHitCounters(): bool {
        $oldGlobalFile    = $this->dataDir . '/global.json';
        $oldUserHitsFile  = $this->dataDir . '/user_hits.json';

        $hasOldGlobal    = file_exists($oldGlobalFile);
        $hasOldUserHits  = file_exists($oldUserHitsFile);

        if (!$hasOldGlobal && !$hasOldUserHits) {
            return false; // Nothing to migrate
        }

        $oldGlobal   = $hasOldGlobal    ? $this->readJson($oldGlobalFile)   : [];
        $oldUserHits = $hasOldUserHits  ? $this->readJson($oldUserHitsFile) : [];

        $this->lockedUpdate($this->hitCountsFile, function (&$data) use ($oldGlobal, $oldUserHits) {
            $this->ensureHitCountsStructure($data);

            // Only migrate if current hit_counts is at zero (fresh)
            if ((int)($data['global']['total_hits'] ?? 0) === 0 && empty($data['users'])) {
                $data['global']['total_hits'] = (int)($oldGlobal['total_hits'] ?? 0);
                foreach ($oldUserHits as $uid => $count) {
                    $data['users'][(string)$uid] = (int)$count;
                }
            }
        });

        // Remove old files after successful migration
        if ($hasOldGlobal)   @unlink($oldGlobalFile);
        if ($hasOldUserHits) @unlink($oldUserHitsFile);

        return true;
    }

    /**
     * Read the global hit count (O(1), no user scan).
     */
    public function getGlobalHitCount(): int {
        $data = $this->readJson($this->hitCountsFile);
        $this->ensureHitCountsStructure($data);
        return (int)($data['global']['total_hits'] ?? 0);
    }

    /**
     * Read a single user's hit count (O(1) lookup).
     */
    public function getUserHitCount($userId): int {
        $data = $this->readJson($this->hitCountsFile);
        $this->ensureHitCountsStructure($data);
        return (int)($data['users'][(string)$userId] ?? 0);
    }

    /**
     * Read both global and user hit count in ONE read (O(1)).
     * Returns ['global_hits' => int, 'user_hits' => int]
     */
    public function getHitCounts($userId = null): array {
        $data = $this->readJson($this->hitCountsFile);
        $this->ensureHitCountsStructure($data);

        $result = [
            'global_hits' => (int)($data['global']['total_hits'] ?? 0),
            'user_hits'   => 0
        ];

        if ($userId) {
            $result['user_hits'] = (int)($data['users'][(string)$userId] ?? 0);
        }

        return $result;
    }

    /**
     * Atomically increment BOTH global and user hit counters in ONE write.
     * This is the key fix -- no more separate file writes that can desync.
     */
    public function incrementHitCounts($userId): array {
        $needle = (string)$userId;

        return $this->lockedUpdate($this->hitCountsFile, function (&$data) use ($needle) {
            $this->ensureHitCountsStructure($data);

            // Increment global
            $data['global']['total_hits'] = (int)($data['global']['total_hits'] ?? 0) + 1;

            // Increment user
            $data['users'][$needle] = (int)($data['users'][$needle] ?? 0) + 1;

            return [
                'global_hits' => $data['global']['total_hits'],
                'user_hits'   => $data['users'][$needle]
            ];
        });
    }

    /**
     * Rebuild hit_counts.json from users.json (use after migration or reset).
     */
    public function rebuildHitCounters(): array {
        $users = $this->readJson($this->usersFile);
        $globalTotal = 0;
        $userHits = [];

        foreach ($users as $u) {
            $hits = (int)($u['hits'] ?? 0);
            $globalTotal += $hits;
            if ($hits > 0) {
                $userHits[(string)$u['user_id']] = $hits;
            }
        }

        $this->lockedUpdate($this->hitCountsFile, function (&$data) use ($globalTotal, $userHits) {
            $data = [
                'global' => ['total_hits' => $globalTotal],
                'users'  => $userHits
            ];
        });

        return ['total_hits' => $globalTotal, 'users_with_hits' => count($userHits)];
    }

    /**
     * Auto-sync: compare users.json total with hit_counts.json global.
     * If they differ, rebuild hit_counts.json from users.json (source of truth).
     * Called on every API request -- cheap O(n) read, write only when out of sync.
     */
    public function autoSyncHitCounters(): void {
        $users = $this->readJson($this->usersFile);
        $usersTotal = 0;
        foreach ($users as $u) {
            $usersTotal += (int)($u['hits'] ?? 0);
        }

        $data = $this->readJson($this->hitCountsFile);
        $this->ensureHitCountsStructure($data);
        $countersTotal = (int)($data['global']['total_hits'] ?? 0);

        if ($usersTotal !== $countersTotal) {
            $this->rebuildHitCounters();
        }
    }

    /**
     * Reset hit counters to zero.
     */
    public function resetHitCounters(): void {
        $this->lockedUpdate($this->hitCountsFile, function (&$data) {
            $data = [
                'global' => ['total_hits' => 0],
                'users'  => []
            ];
        });
    }

    /* ─── Hits ─── */

    public function addHitRecord($userId, array $details): bool {
        return (bool) $this->lockedUpdate($this->hitsFile, function (&$hits) use ($userId, $details) {
            $hits[] = [
                'user_id'   => (string)$userId,
                'full_card' => $details['full_card'] ?? '',
                'amount'    => $details['amount'] ?: '0',
                'currency'  => $details['currency'] ?? 'usd',
                'merchant'  => $details['merchant'] ?? '',
                'timestamp' => date('c')
            ];
            return true;
        });
    }

    public function getUserHits($userId, int $limit = 50): array {
        $hits = $this->readJson($this->hitsFile);
        $needle = (string)$userId;
        $result = [];
        foreach ($hits as $h) {
            if ((string)($h['user_id'] ?? '') === $needle) {
                $result[] = $h;
            }
        }
        return array_slice(array_reverse($result), 0, $limit);
    }

    /**
     * Get the total number of hit records for a user (no limit).
     */
    public function getUserHitsTotal($userId): int {
        $hits = $this->readJson($this->hitsFile);
        $needle = (string)$userId;
        $count = 0;
        foreach ($hits as $h) {
            if ((string)($h['user_id'] ?? '') === $needle) {
                $count++;
            }
        }
        return $count;
    }

    public function cleanFakeHits(): int {
        return $this->lockedUpdate($this->hitsFile, function (&$hits) {
            $before = count($hits);
            $hits = array_values(array_filter($hits, function ($h) {
                $card = $h['full_card'] ?? '';
                return strlen($card) >= 13 && strpos($card, '|') !== false;
            }));
            return $before - count($hits);
        });
    }

    /* ─── License Keys ─── */

    public function validateLicenseKey(string $key): array {
        $keys = $this->readJson($this->keysFile);
        foreach ($keys as $k) {
            if (($k['key'] ?? '') === $key && !empty($k['active'])) {
                return ['valid' => true, 'version' => $k['version'] ?? ''];
            }
        }
        return ['valid' => false];
    }

    public function createLicenseKey(string $key, string $version, bool $active = true): bool {
        return (bool) $this->lockedUpdate($this->keysFile, function (&$keys) use ($key, $version, $active) {
            $keys[] = [
                'key'        => $key,
                'version'    => $version,
                'active'     => $active,
                'created_at' => date('c')
            ];
            return true;
        });
    }

    public function getAllLicenseKeys(): array {
        return $this->readJson($this->keysFile);
    }

    public function revokeLicenseKey(string $key): bool {
        return $this->lockedUpdate($this->keysFile, function (&$keys) use ($key) {
            foreach ($keys as &$k) {
                if (($k['key'] ?? '') === $key) {
                    $k['active'] = false;
                    return true;
                }
            }
            return false;
        });
    }

    public function activateLicenseKey(string $key): bool {
        return $this->lockedUpdate($this->keysFile, function (&$keys) use ($key) {
            foreach ($keys as &$k) {
                if (($k['key'] ?? '') === $key) {
                    $k['active'] = true;
                    return true;
                }
            }
            return false;
        });
    }

    public function deleteLicenseKey(string $key): bool {
        return $this->lockedUpdate($this->keysFile, function (&$keys) use ($key) {
            $before = count($keys);
            $keys = array_values(array_filter($keys, function ($k) use ($key) {
                return ($k['key'] ?? '') !== $key;
            }));
            return count($keys) < $before;
        });
    }

    /* ─── Settings ─── */

    public function getSetting(string $name) {
        $settings = $this->readJson($this->settingsFile);
        return $settings[$name] ?? null;
    }

    public function setSetting(string $name, $value): bool {
        return (bool) $this->lockedUpdate($this->settingsFile, function (&$settings) use ($name, $value) {
            $settings[$name] = $value;
            return true;
        });
    }

    public function getAllSettings(): array {
        return $this->readJson($this->settingsFile);
    }

    /* ─── BIN Library ─── */

    public function getBinLibrary(): array {
        return $this->readJson($this->binLibraryFile);
    }

    public function saveBinLibrary(array $bins): bool {
        $lockFp = $this->acquireLock($this->binLibraryFile, LOCK_EX);
        $ok = $this->atomicWrite($this->binLibraryFile, $bins);
        if ($lockFp) { $this->releaseLock($this->binLibraryFile); }
        return $ok;
    }

    public function addBinToLibrary(array $binData): bool {
        return (bool) $this->lockedUpdate($this->binLibraryFile, function (&$bins) use ($binData) {
            $bins[] = $binData;
            return true;
        });
    }

    public function removeBinFromLibrary($binId = null, $binNumber = null) {
        return $this->lockedUpdate($this->binLibraryFile, function (&$bins) use ($binId, $binNumber) {
            $removedBin = null;
            $newBins = [];
            foreach ($bins as $b) {
                $shouldRemove = false;
                if ($binId && isset($b['id']) && $b['id'] === $binId) {
                    $shouldRemove = true;
                }
                if ($binNumber && isset($b['bin']) && $b['bin'] === $binNumber) {
                    $shouldRemove = true;
                }
                if ($shouldRemove && $removedBin === null) {
                    $removedBin = $b;
                } else {
                    $newBins[] = $b;
                }
            }
            $bins = $newBins;
            return $removedBin;
        });
    }

    public function clearBinLibrary(): bool {
        $lockFp = $this->acquireLock($this->binLibraryFile, LOCK_EX);
        $ok = $this->atomicWrite($this->binLibraryFile, []);
        if ($lockFp) { $this->releaseLock($this->binLibraryFile); }
        return $ok;
    }

    /* ─── Bulk Admin ─── */

    public function clearAllTokensAndStats(): int {
        $count = $this->lockedUpdate($this->usersFile, function (&$users) {
            foreach ($users as &$user) {
                $user['token']    = null;
                $user['hits']     = 0;
                $user['attempts'] = 0;
            }
            return count($users);
        });
        $this->resetHitCounters();
        return $count;
    }

    public function resetDatabase(): array {
        $deleted = [
            'users' => count($this->readJson($this->usersFile)),
            'hits'  => count($this->readJson($this->hitsFile)),
            'keys'  => count($this->readJson($this->keysFile))
        ];

        $this->lockedUpdate($this->usersFile, function (&$d) { $d = []; });
        $this->lockedUpdate($this->hitsFile,  function (&$d) { $d = []; });
        $this->lockedUpdate($this->keysFile,  function (&$d) { $d = []; });
        $this->resetHitCounters();

        return $deleted;
    }
}
