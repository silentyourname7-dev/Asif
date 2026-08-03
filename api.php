<?php


/* ─── Headers ─── */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With');
header('X-Content-Type-Options: nosniff');

/* ─── Error handling ─── */
error_reporting(E_ALL);
ini_set('display_errors', 0);
ini_set('log_errors', 1);
ini_set('error_log', __DIR__ . '/error.log');

set_exception_handler(function (Throwable $e) {
    error_log("[API] Uncaught exception: " . $e->getMessage() . " in " . $e->getFile() . ":" . $e->getLine());
    http_response_code(500);
    echo json_encode([
        'success' => false,
        'error'   => 'Internal server error'
    ]);
    exit;
});

set_error_handler(function ($severity, $message, $file, $line) {
    if (!(error_reporting() & $severity)) return false;
    throw new ErrorException($message, 0, $severity, $file, $line);
});

/* ─── Pre-flight ─── */
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

/* ─── Bootstrap ─── */
require_once __DIR__ . '/database.php';

$db = new Database(__DIR__ . '/data');

/* ─── Auto-migrate old files and keep hit_counts.json in sync with users.json ─── */
$db->migrateOldHitCounters();
$db->autoSyncHitCounters();

/* ─── Helpers ─── */

function apiResponse(bool $success, array $data = [], $error = null, int $status = 200): void {
    http_response_code($status);
    $response = ['success' => $success];
    if ($data)  { $response = array_merge($response, $data); }
    if ($error) { $response['error'] = $error; }
    echo json_encode($response, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function getJsonBody(): array {
    static $cache = null;
    if ($cache !== null) return $cache;
    $raw = file_get_contents('php://input');
    if ($raw) {
        $decoded = json_decode($raw, true);
        $cache = is_array($decoded) ? $decoded : [];
    } else {
        $cache = [];
    }
    return $cache;
}

function getInput(string $key, $default = null) {
    // Query-string first, then POST body, then JSON body
    if (isset($_GET[$key]))  return trim((string)$_GET[$key]);
    if (isset($_POST[$key])) return trim((string)$_POST[$key]);
    $json = getJsonBody();
    if (isset($json[$key]))  return is_string($json[$key]) ? trim($json[$key]) : $json[$key];
    return $default;
}

function sanitize(string $input, int $maxLen = 500): string {
    $input = trim($input);
    $input = strip_tags($input);
    if (strlen($input) > $maxLen) {
        $input = substr($input, 0, $maxLen);
    }
    return $input;
}

function generateToken(int $length = 15): string {
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    $token = '';
    for ($i = 0; $i < $length; $i++) {
        $token .= $chars[random_int(0, strlen($chars) - 1)];
    }
    return $token;
}

function generateLicenseKey(string $version): string {
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    $random = '';
    for ($i = 0; $i < 20; $i++) {
        $random .= $chars[random_int(0, strlen($chars) - 1)];
    }
    return 'USAGI-' . str_replace('.', '', $version) . '-' . $random;
}

function requireToken(): array {
    global $db;
    $token = getInput('token');
    if (!$token)              apiResponse(false, [], 'Token required', 400);
    if (strlen($token) !== 15) apiResponse(false, [], 'Invalid token format (must be 15 chars)', 400);

    $user = $db->getUserByToken($token);
    if (!$user)               apiResponse(false, [], 'Invalid token', 401);
    if (!empty($user['banned'])) apiResponse(false, [], 'Account suspended', 403);

    return $user;
}

/**
 * Concurrency-safe feedback file read/write.
 * Uses its own lock so parallel bin-feedback requests don't collide.
 */
function readFeedback(string $path): array {
    if (!file_exists($path)) return [];
    $lockFile = $path . '.lock';
    $lf = @fopen($lockFile, 'c');
    if ($lf) flock($lf, LOCK_SH);
    $raw = @file_get_contents($path);
    if ($lf) { flock($lf, LOCK_UN); fclose($lf); }
    return ($raw !== false) ? (json_decode($raw, true) ?: []) : [];
}

function writeFeedback(string $path, array $data): bool {
    $lockFile = $path . '.lock';
    $lf = @fopen($lockFile, 'c');
    if ($lf) flock($lf, LOCK_EX);

    // Re-read inside the lock to merge any concurrent changes
    $tmp = $path . '.tmp.' . getmypid();
    $json = json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
    $ok = @file_put_contents($tmp, $json);
    if ($ok !== false) {
        if (!@rename($tmp, $path)) {
            @copy($tmp, $path);
            @unlink($tmp);
        }
    }

    if ($lf) { flock($lf, LOCK_UN); fclose($lf); }
    return $ok !== false;
}

/* ─── Router ─── */

$action = getInput('action', '');
$method = $_SERVER['REQUEST_METHOD'];

switch ($action) {

    /* ── Public ── */

    case '':
    case 'index':
        apiResponse(true, [
            'service' => 'UsagiAutoX API',
            'version' => '2.5',
            'status'  => 'online'
        ]);
        break;

    case 'health':
        apiResponse(true, [
            'status'           => 'healthy',
            'timestamp'        => date('c'),
            'data_dir_writable'=> is_writable(__DIR__ . '/data')
        ]);
        break;

    /* ── License key check ── */

    case 'check-key':
        $key = getInput('key');
        if (!$key) apiResponse(false, [], 'License key required', 400);

        $result          = $db->validateLicenseKey($key);
        $telegramChannel = $db->getSetting('telegram_channel') ?: 'https://t.me/UsagiAutoX';
        $latestVersion   = $db->getSetting('latest_version')   ?: '1.0.7';

        if (!empty($result['valid'])) {
            apiResponse(true, [
                'valid'            => true,
                'version'          => $result['version'] ?? '',
                'latest_version'   => $latestVersion,
                'message'          => 'License key is valid',
                'telegram_channel' => $telegramChannel
            ]);
        } else {
            apiResponse(false, [
                'valid'            => false,
                'latest_version'   => $latestVersion,
                'message'          => 'Invalid or expired license key.',
                'telegram_channel' => $telegramChannel
            ], null, 403);
        }
        break;

    /* ── Token validation ── */

    case 'validate':
        $token = getInput('token');
        if (!$token)               apiResponse(false, [], 'Token required', 400);
        if (strlen($token) !== 15) apiResponse(false, [], 'Token must be 15 characters', 400);

        $user = $db->getUserByToken($token);
        if (!$user)                   apiResponse(false, [], 'Invalid token', 401);
        if (!empty($user['banned']))  apiResponse(false, [], 'Account suspended', 403);

    $db->updateUser($user['user_id'], ['last_active' => date('c')]);

    // Read authoritative hit counts from hit_counts.json
    $counts = $db->getHitCounts($user['user_id']);

    apiResponse(true, [
        'user_id'     => (string)$user['user_id'],
        'username'    => $user['username'] ?? '',
        'first_name'  => $user['first_name'] ?? '',
        'pfp_url'     => $user['pfp_url'] ?? '',
        'hits'        => $counts['user_hits'],
        'attempts'    => (int)($user['attempts'] ?? 0),
        'global_hits' => $counts['global_hits'],
        'user_hits'   => $counts['user_hits']
    ]);
    break;

    /* ── Attempt ── */

    case 'attempt':
        $user        = requireToken();
        $newAttempts = $db->incrementStat($user['user_id'], 'attempts');
        apiResponse(true, [
            'user_id'  => (string)$user['user_id'],
            'attempts' => $newAttempts,
            'message'  => 'Attempt recorded'
        ]);
        break;

    /* ── Hit ── */

    case 'hit':
        $user = requireToken();

        $fullCard = getInput('full_card', '');
        $currency = getInput('currency', 'usd');
        if (!$currency || $currency === 'null') $currency = 'usd';

        if (!$fullCard || $fullCard === 'null' || strlen($fullCard) < 13 || strpos($fullCard, '|') === false) {
            apiResponse(false, [], 'Invalid card data: ' . ($fullCard ?: 'empty'), 400);
        }

        $rawAmount = getInput('amount', '0') ?: '0';
        $details = [
            'full_card' => sanitize($fullCard, 100),
            'amount'    => sanitize($rawAmount, 20),
            'currency'  => sanitize($currency, 10),
            'merchant'  => sanitize(getInput('merchant', '') ?: '', 100)
        ];

        $newHits = $db->incrementStat($user['user_id'], 'hits');
        $db->addHitRecord($user['user_id'], $details);

        // Read latest counts from hit_counts.json for immediate UI update
        $counts = $db->getHitCounts($user['user_id']);

        apiResponse(true, [
            'user_id'     => (string)$user['user_id'],
            'hits'        => $counts['user_hits'],
            'global_hits' => $counts['global_hits'],
            'user_hits'   => $counts['user_hits'],
            'message'     => 'Hit recorded successfully'
        ]);
        break;

    /* ── User info ── */

    case 'user':
        $userId = getInput('user_id');
        if (!$userId) apiResponse(false, [], 'User ID required', 400);

        $user = $db->getUser($userId);
        if (!$user)   apiResponse(false, [], 'User not found', 404);

        apiResponse(true, [
            'user_id'  => (string)$user['user_id'],
            'username' => $user['username'] ?? '',
            'pfp_url'  => $user['pfp_url'] ?? '',
            'hits'     => (int)($user['hits'] ?? 0),
            'attempts' => (int)($user['attempts'] ?? 0)
        ]);
        break;

    /* ── Public stats ── */

    case 'stats':
        $stats = $db->getGlobalStats();
        apiResponse(true, [
            'total_users'    => $stats['total_users'] ?? 0,
            'total_attempts' => $stats['total_attempts'] ?? 0,
            'total_hits'     => $stats['total_hits'] ?? 0
        ]);
        break;

    /* ── Leaderboard ── */

    case 'leaderboard':
        $limit       = max(1, min(50, (int)getInput('limit', 10)));
        $topUsers    = $db->getTopUsers($limit);
        $leaderboard = [];
        foreach ($topUsers as $i => $u) {
            $leaderboard[] = [
                'rank'       => $i + 1,
                'user_id'    => (string)$u['user_id'],
                'username'   => $u['username'] ?? '',
                'first_name' => $u['first_name'] ?? '',
                'pfp_url'    => $u['pfp_url'] ?? '',
                'hits'       => (int)($u['hits'] ?? 0)
            ];
        }

        // If a token or user_id is provided, include the requester's rank
        $reqUserId = getInput('user_id');
        $reqToken  = getInput('token');
        if ($reqToken && strlen($reqToken) === 15) {
            $reqUser = $db->getUserByToken($reqToken);
            if ($reqUser) $reqUserId = (string)$reqUser['user_id'];
        }

        $myRank = null;
        if ($reqUserId) {
            $rankInfo = $db->getUserRank($reqUserId);
            if ($rankInfo) {
                $myRank = $rankInfo;
            }
        }

        $response = ['leaderboard' => $leaderboard];
        if ($myRank) {
            $response['my_rank'] = $myRank;
        }

        apiResponse(true, $response);
        break;

    /* ── Popup dashboard stats (lightweight, no auth) ── */

    case 'popup-stats':
        $users = $db->getAllUsers();
        $hits  = $db->getAllHits();

        $today   = date('Y-m-d');
        $weekAgo = date('Y-m-d', strtotime('-7 days'));
        $hitsToday = $hitsWeek = 0;

        foreach ($hits as $h) {
            $d = substr($h['timestamp'] ?? '', 0, 10);
            if ($d === $today)  $hitsToday++;
            if ($d >= $weekAgo) $hitsWeek++;
        }

        apiResponse(true, [
            'total_users' => count($users),
            'total_hits'  => count($hits),
            'hits_today'  => $hitsToday,
            'hits_week'   => $hitsWeek
        ]);
        break;

    /* ── Hit counts (global + user) ── */

    case 'hit-counts':
        $token  = getInput('token');
        $userId = getInput('user_id');

        // Resolve user_id from token if provided
        if ($token && strlen($token) === 15) {
            $user = $db->getUserByToken($token);
            if ($user && empty($user['banned'])) {
                $userId = (string)$user['user_id'];
            }
        }

        // Single O(1) read from hit_counts.json -- both global + user
        $counts = $db->getHitCounts($userId ?: null);

        apiResponse(true, [
            'global_hits' => $counts['global_hits'],
            'user_hits'   => $counts['user_hits']
        ]);
        break;

    /* ── User hits history ── */

    case 'user-hits':
        $user  = requireToken();
        $limit = max(1, min(500, (int)getInput('limit', 50)));
        $allUserHits = $db->getUserHits($user['user_id'], $limit);
        $totalCount  = $db->getUserHitsTotal($user['user_id']);
        apiResponse(true, [
            'user_id'     => (string)$user['user_id'],
            'hits'        => $allUserHits,
            'total_count' => $totalCount
        ]);
        break;

    /* ── Create user ── */

    case 'create-user':
        $userId    = getInput('user_id');
        $username  = sanitize(getInput('username', '') ?: '', 100);
        $firstName = sanitize(getInput('first_name', '') ?: '', 100);
        $pfpUrl    = sanitize(getInput('pfp_url', '') ?: '', 500);
        if (!$userId) apiResponse(false, [], 'User ID required', 400);

        $existingUser = $db->getUser($userId);
        if ($existingUser) {
            // Update pfp_url, username, first_name if provided
            $updates = [];
            if ($pfpUrl)    $updates['pfp_url']    = $pfpUrl;
            if ($username)  $updates['username']   = $username;
            if ($firstName) $updates['first_name'] = $firstName;
            if (!empty($updates)) $db->updateUser($userId, $updates);

            apiResponse(true, [
                'user_id' => (string)$existingUser['user_id'],
                'message' => 'User already exists',
                'token'   => $existingUser['token'] ?? null
            ]);
        }

        $user = $db->createUser([
            'user_id'    => $userId,
            'username'   => $username,
            'first_name' => $firstName,
            'pfp_url'    => $pfpUrl
        ]);
        apiResponse(true, [
            'user_id' => (string)$user['user_id'],
            'message' => 'User created'
        ]);
        break;

    /* ── Generate token ── */

    case 'generate-token':
        $userId   = getInput('user_id');
        $forceNew = getInput('force_new', 'false') === 'true';
        if (!$userId) apiResponse(false, [], 'User ID required', 400);

        $user = $db->getUser($userId);
        if (!$user)   apiResponse(false, [], 'User not found', 404);

        if ($forceNew || empty($user['token'])) {
            $token = generateToken();
            $maxRetries = 10;
            while ($db->isTokenExists($token) && $maxRetries-- > 0) {
                $token = generateToken();
            }
            $db->updateUser($userId, ['token' => $token]);
            apiResponse(true, [
                'user_id' => (string)$userId,
                'token'   => $token,
                'message' => $forceNew ? 'Token regenerated' : 'New token generated'
            ]);
        } else {
            apiResponse(true, [
                'user_id' => (string)$userId,
                'token'   => $user['token'],
                'message' => 'Existing token returned'
            ]);
        }
        break;

    /* ── BIN library (public) ─��� */

    case 'bin-library':
        $bins = $db->getBinLibrary();
        $userId = getInput('user_id');

        $feedbackFile = __DIR__ . '/feedback.json';
        $allFeedback  = readFeedback($feedbackFile);

        $needsUpdate = false;
        foreach ($bins as &$bin) {
            if (!isset($bin['id']) || empty($bin['id'])) {
                $bin['id'] = uniqid('bin_');
                $needsUpdate = true;
            }
            $binId = $bin['id'];
            if (isset($allFeedback[$binId])) {
                $bin['likes']    = (int)($allFeedback[$binId]['likes'] ?? 0);
                $bin['dislikes'] = (int)($allFeedback[$binId]['dislikes'] ?? 0);
                $bin['user_vote'] = ($userId && isset($allFeedback[$binId]['voters'][$userId]['vote']))
                    ? $allFeedback[$binId]['voters'][$userId]['vote']
                    : null;
            } else {
                $bin['likes']     = 0;
                $bin['dislikes']  = 0;
                $bin['user_vote'] = null;
            }
        }
        unset($bin);

        if ($needsUpdate) {
            $db->saveBinLibrary($bins);
        }
        apiResponse(true, ['bins' => $bins]);
        break;

    /* ── BIN feedback (concurrent-safe) ── */

    case 'bin-feedback':
        $binId    = getInput('id');
        $vote     = getInput('vote');
        $userId   = getInput('user_id');
        $userName = sanitize(getInput('user_name', '') ?: '', 100);

        if (!$binId || !$vote || !$userId) {
            apiResponse(false, [], 'ID, vote, and user_id required', 400);
        }
        if (!in_array($vote, ['like', 'dislike'], true)) {
            apiResponse(false, [], 'Vote must be "like" or "dislike"', 400);
        }

        $feedbackFile = __DIR__ . '/feedback.json';

        // Lock, re-read, mutate, write - fully atomic
        $lockFile = $feedbackFile . '.lock';
        $lf = @fopen($lockFile, 'c');
        if ($lf) flock($lf, LOCK_EX);

        $feedback = [];
        if (file_exists($feedbackFile)) {
            $raw = @file_get_contents($feedbackFile);
            $feedback = ($raw !== false) ? (json_decode($raw, true) ?: []) : [];
        }

        if (!isset($feedback[$binId])) {
            $feedback[$binId] = ['likes' => 0, 'dislikes' => 0, 'voters' => []];
        }
        if (!isset($feedback[$binId]['voters'])) {
            $feedback[$binId]['voters'] = [];
        }

        $previousVote = $feedback[$binId]['voters'][$userId]['vote'] ?? null;

        // Already voted the same
        if ($previousVote === $vote) {
            if ($lf) { flock($lf, LOCK_UN); fclose($lf); }
            apiResponse(true, [
                'message'   => 'Already voted',
                'likes'     => (int)$feedback[$binId]['likes'],
                'dislikes'  => (int)$feedback[$binId]['dislikes'],
                'user_vote' => $vote,
                'id'        => $binId
            ]);
        }

        // Undo previous vote
        if ($previousVote === 'like') {
            $feedback[$binId]['likes'] = max(0, (int)$feedback[$binId]['likes'] - 1);
        } elseif ($previousVote === 'dislike') {
            $feedback[$binId]['dislikes'] = max(0, (int)$feedback[$binId]['dislikes'] - 1);
        }

        // Apply new vote
        if ($vote === 'like') {
            $feedback[$binId]['likes'] = (int)$feedback[$binId]['likes'] + 1;
        } elseif ($vote === 'dislike') {
            $feedback[$binId]['dislikes'] = (int)$feedback[$binId]['dislikes'] + 1;
        }

        $feedback[$binId]['voters'][$userId] = [
            'vote' => $vote,
            'name' => $userName ?: 'Unknown',
            'time' => date('Y-m-d H:i:s')
        ];

        // Atomic write
        $tmp = $feedbackFile . '.tmp.' . getmypid();
        @file_put_contents($tmp, json_encode($feedback, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
        if (!@rename($tmp, $feedbackFile)) {
            @copy($tmp, $feedbackFile);
            @unlink($tmp);
        }

        if ($lf) { flock($lf, LOCK_UN); fclose($lf); }

        apiResponse(true, [
            'message'      => 'Feedback recorded',
            'likes'        => (int)$feedback[$binId]['likes'],
            'dislikes'     => (int)$feedback[$binId]['dislikes'],
            'user_vote'    => $vote,
            'id'           => $binId,
            'changed_from' => $previousVote
        ]);
        break;

    /* ═══════════════════ Admin endpoints ═══════════════════ */

    case 'admin-genkey':
        $version = getInput('version');
        if (!$version) apiResponse(false, [], 'Version required', 400);

        $key = generateLicenseKey($version);
        $db->createLicenseKey($key, $version, true);
        apiResponse(true, [
            'key'     => $key,
            'version' => $version,
            'active'  => true
        ]);
        break;

    case 'admin-listkeys':
        apiResponse(true, ['keys' => $db->getAllLicenseKeys()]);
        break;

    case 'admin-revokekey':
        $key = getInput('key');
        if (!$key) apiResponse(false, [], 'Key required', 400);
        $db->revokeLicenseKey($key)
            ? apiResponse(true, ['message' => 'Key revoked', 'key' => $key])
            : apiResponse(false, [], 'Key not found', 404);
        break;

    case 'admin-activatekey':
        $key = getInput('key');
        if (!$key) apiResponse(false, [], 'Key required', 400);
        $db->activateLicenseKey($key)
            ? apiResponse(true, ['message' => 'Key activated', 'key' => $key])
            : apiResponse(false, [], 'Key not found', 404);
        break;

    case 'admin-deletekey':
        $key = getInput('key');
        if (!$key) apiResponse(false, [], 'Key required', 400);
        $db->deleteLicenseKey($key)
            ? apiResponse(true, ['message' => 'Key deleted', 'key' => $key])
            : apiResponse(false, [], 'Key not found', 404);
        break;

    case 'admin-setsetting':
        $name  = getInput('name');
        $value = getInput('value');
        if (!$name) apiResponse(false, [], 'Setting name required', 400);
        $db->setSetting($name, $value);
        apiResponse(true, ['message' => 'Setting saved', 'name' => $name, 'value' => $value]);
        break;

    case 'admin-getsettings':
        apiResponse(true, ['settings' => $db->getAllSettings()]);
        break;

    case 'admin-cleartokens':
        $count = $db->clearAllTokensAndStats();
        apiResponse(true, ['message' => 'Tokens and stats cleared', 'users_reset' => $count]);
        break;

    case 'admin-cleanfakehits':
        $deleted = $db->cleanFakeHits();
        apiResponse(true, ['message' => 'Fake hits cleaned', 'deleted' => $deleted]);
        break;

    case 'admin-resetdb':
        if (getInput('confirm') !== 'yes') {
            apiResponse(false, [], 'Add confirm=yes to reset database', 400);
        }
        $result = $db->resetDatabase();
        apiResponse(true, ['message' => 'Database reset complete', 'deleted' => $result]);
        break;

    case 'admin-banuser':
        $userId = getInput('user_id');
        if (!$userId) apiResponse(false, [], 'User ID required', 400);
        $db->updateUser($userId, ['banned' => true])
            ? apiResponse(true, ['message' => 'User banned', 'user_id' => $userId])
            : apiResponse(false, [], 'User not found', 404);
        break;

    case 'admin-unbanuser':
        $userId = getInput('user_id');
        if (!$userId) apiResponse(false, [], 'User ID required', 400);
        $db->updateUser($userId, ['banned' => false])
            ? apiResponse(true, ['message' => 'User unbanned', 'user_id' => $userId])
            : apiResponse(false, [], 'User not found', 404);
        break;

    case 'admin-allusers':
        apiResponse(true, ['users' => $db->getAllUsers()]);
        break;

    case 'admin-keyinfo':
        $keys  = $db->getAllLicenseKeys();
        $users = $db->getAllUsers();

        $activeKeys = $revokedKeys = 0;
        $versionCount = [];
        foreach ($keys as $k) {
            !empty($k['active']) ? $activeKeys++ : $revokedKeys++;
            $ver = $k['version'] ?? 'unknown';
            $versionCount[$ver] = ($versionCount[$ver] ?? 0) + 1;
        }

        apiResponse(true, [
            'stats' => [
                'total_keys'   => count($keys),
                'active_keys'  => $activeKeys,
                'revoked_keys' => $revokedKeys,
                'total_users'  => count($users),
                'versions'     => $versionCount,
                'top_users'    => $db->getTopUsers(5)
            ]
        ]);
        break;

    case 'admin-stats':
        $users = $db->getAllUsers();
        $keys  = $db->getAllLicenseKeys();
        $hits  = $db->getAllHits();
        $bins  = $db->getBinLibrary();

        $activeKeys = $revokedKeys = 0;
        foreach ($keys as $k) {
            !empty($k['active']) ? $activeKeys++ : $revokedKeys++;
        }

        $today   = date('Y-m-d');
        $weekAgo = date('Y-m-d', strtotime('-7 days'));
        $hitsToday = $hitsWeek = 0;
        $activeToday = [];

        foreach ($hits as $h) {
            $d = substr($h['timestamp'] ?? '', 0, 10);
            if ($d === $today)   $hitsToday++;
            if ($d >= $weekAgo)  $hitsWeek++;
        }
        foreach ($users as $u) {
            if (substr($u['last_active'] ?? '', 0, 10) === $today) {
                $activeToday[$u['user_id']] = true;
            }
        }

        apiResponse(true, [
            'stats' => [
                'total_users'  => count($users),
                'active_today' => count($activeToday),
                'total_keys'   => count($keys),
                'active_keys'  => $activeKeys,
                'revoked_keys' => $revokedKeys,
                'total_hits'   => count($hits),
                'hits_today'   => $hitsToday,
                'hits_week'    => $hitsWeek,
                'total_bins'   => count($bins)
            ]
        ]);
        break;

    case 'admin-allhits':
        apiResponse(true, ['hits' => $db->getAllHits()]);
        break;

    case 'admin-addbin':
        $site   = sanitize(getInput('site', 'Unknown') ?: 'Unknown', 200);
        $bin    = getInput('bin');
        $credit = sanitize(getInput('credit', 'Unknown') ?: 'Unknown', 200);
        if (!$bin) apiResponse(false, [], 'BIN is required', 400);

        $newBin = [
            'id'       => uniqid('bin_'),
            'site'     => $site,
            'bin'      => sanitize($bin, 20),
            'credit'   => $credit,
            'likes'    => 0,
            'dislikes' => 0,
            'added_at' => (new DateTime('now', new DateTimeZone('Asia/Kolkata')))->format('Y-m-d H:i:s')
        ];

        $db->addBinToLibrary($newBin)
            ? apiResponse(true, ['message' => 'BIN added to library', 'bin' => $newBin])
            : apiResponse(false, [], 'Failed to add BIN', 500);
        break;

    case 'admin-removebin':
        $binId     = getInput('bin_id');
        $binNumber = getInput('bin');
        if (!$binId && !$binNumber) apiResponse(false, [], 'BIN ID or BIN number required', 400);

        $removed = $db->removeBinFromLibrary($binId, $binNumber);
        $removed
            ? apiResponse(true, [
                'message' => 'BIN removed from library',
                'bin'     => $removed['bin'] ?? 'N/A',
                'site'    => $removed['site'] ?? 'N/A',
                'id'      => $removed['id'] ?? $binId
            ])
            : apiResponse(false, [], 'BIN not found', 404);
        break;

    case 'admin-rebuild-hits':
        $result = $db->rebuildHitCounters();
        apiResponse(true, [
            'message'         => 'Hit counters rebuilt from users.json',
            'total_hits'      => $result['total_hits'],
            'users_with_hits' => $result['users_with_hits']
        ]);
        break;

    case 'admin-clearbin':
        $db->clearBinLibrary()
            ? apiResponse(true, ['message' => 'BIN library cleared'])
            : apiResponse(false, [], 'Failed to clear library', 500);
        break;

    case 'debug':
        $users = $db->getAllUsers();
        $hits  = $db->getAllHits();
        apiResponse(true, [
            'users_count'       => count($users),
            'hits_count'        => count($hits),
            'data_dir'          => __DIR__ . '/data',
            'data_dir_exists'   => is_dir(__DIR__ . '/data'),
            'data_dir_writable' => is_writable(__DIR__ . '/data'),
            'users_file_exists' => file_exists(__DIR__ . '/data/users.json'),
            'hits_file_exists'  => file_exists(__DIR__ . '/data/hits.json'),
            'php_version'       => PHP_VERSION,
            'users'             => $users,
            'recent_hits'       => array_slice($hits, -5)
        ]);
        break;

    default:
        apiResponse(false, [], 'Unknown action: ' . sanitize($action, 50), 400);
        break;
}
