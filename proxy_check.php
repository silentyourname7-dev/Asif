<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

$rawProxy = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {

    $input = file_get_contents('php://input');
    $data = json_decode($input, true);
    $rawProxy = $data['proxy'] ?? '';
} else {

    $queryString = $_SERVER['QUERY_STRING'] ?? '';

    if (strpos($queryString, 'proxy=') === 0) {
        $rawProxy = substr($queryString, 6);
        $rawProxy = urldecode($rawProxy);
    } elseif (isset($_GET['proxy'])) {
        $rawProxy = $_GET['proxy'];
    }
}

if (empty($rawProxy)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'status' => 'fail', 'error' => 'Missing proxy parameter']);
    exit;
}

$parts = explode(":", $rawProxy, 4);
if (count($parts) < 4) {
    http_response_code(400);
    echo json_encode(['success' => false, 'status' => 'fail', 'error' => 'Invalid proxy format. Use host:port:user:pass']);
    exit;
}

$host = $parts[0];
$port = $parts[1];

function checkProxyViaProxyShare($proxyStr) {
    $url = "https://www.proxyshare.com/detection/check";

    $data = [
        'list' => [$proxyStr]
    ];

    $jsonPayload = json_encode($data);

    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 60);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 30);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $jsonPayload);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Content-Type: application/json',
        'User-Agent: Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36'
    ]);
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_ENCODING, '');

    $response = curl_exec($ch);
    $err = curl_error($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($err) {
        return [
            'success' => false,
            'error' => 'cURL error: ' . $err
        ];
    }

    if ($httpCode !== 200) {
        return [
            'success' => false,
            'error' => 'HTTP ' . $httpCode
        ];
    }

    $result = json_decode($response, true);

    if (!is_array($result) || empty($result)) {
        return [
            'success' => false,
            'error' => 'Invalid response'
        ];
    }

    $proxyResult = $result[0];

    if (isset($proxyResult['available']) && $proxyResult['available'] === true) {
        return [
            'success' => true,
            'proxy_ip' => $proxyResult['ip'] ?? 'Unknown',
            'response_time_ms' => $proxyResult['response_time_ms'] ?? 0,
            'country_name' => $proxyResult['country_name'] ?? 'Unknown',
            'country_code' => $proxyResult['country_code'] ?? '',
            'ip_type' => $proxyResult['ip_type'] ?? 'Unknown',
            'types' => $proxyResult['types'] ?? ['HTTP'],
            'proxy_host' => $proxyResult['proxy_host'] ?? '',
            'proxy_port' => $proxyResult['proxy_port'] ?? ''
        ];
    } else {
        return [
            'success' => false,
            'error' => $proxyResult['error'] ?? 'Proxy dead'
        ];
    }
}

$result = checkProxyViaProxyShare($rawProxy);

if ($result['success']) {
    echo json_encode([
        'success' => true,
        'status' => 'success',
        'proxy_ip' => $result['proxy_ip'],
        'response_time_ms' => $result['response_time_ms'],
        'country_name' => $result['country_name'],
        'country_code' => $result['country_code'],
        'ip_type' => $result['ip_type'],
        'types' => $result['types'],
        'proxy_host' => $result['proxy_host'],
        'proxy_port' => $result['proxy_port'],
        'proxy_used' => "$host:$port"
    ]);
} else {
    echo json_encode([
        'success' => false,
        'status' => 'fail',
        'error' => $result['error'],
        'proxy_used' => "$host:$port"
    ]);
}
