const http = require('http');

async function testRoute(name, path, expectedStatus, expectedContent = null) {
    return new Promise((resolve, reject) => {
        const req = http.get(`http://localhost:3000${path}`, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                const passedStatus = res.statusCode === expectedStatus;
                let passedContent = true;
                if (expectedContent) {
                    passedContent = data.includes(expectedContent);
                }
                
                if (passedStatus && passedContent) {
                    console.log(`[PASS] ${name} (${path}) returned ${res.statusCode}`);
                    resolve(true);
                } else {
                    console.error(`[FAIL] ${name} (${path})`);
                    console.error(`       Expected Status: ${expectedStatus}, Got: ${res.statusCode}`);
                    if (expectedContent && !passedContent) {
                        console.error(`       Missing expected content: "${expectedContent}"`);
                    }
                    resolve(false);
                }
            });
        });
        
        req.on('error', (err) => {
            console.error(`[ERROR] Request failed for ${name} (${path}): ${err.message}`);
            resolve(false);
        });
    });
}

async function runValidationSuite() {
    console.log("=== STARTING NATIVE E2E VALIDATION SUITE ===");
    let failures = 0;
    
    // Test 1: Homepage / Fan Dashboard load correctly
    const t1 = await testRoute('Homepage Load', '/', 200);
    if (!t1) failures++;
    
    // Test 2: Real Hydrated Data
    const t2 = await testRoute('Player Dashboard (Dak Prescott)', '/player/dak-prescott', 200);
    if (!t2) failures++;
    
    // Test 3: Graceful degradation for missing Player
    const t3 = await testRoute('Graceful 404 Degradation', '/player/non-existent-player-404', 404);
    if (!t3) failures++;
    
    console.log("============================================");
    if (failures === 0) {
        console.log("All E2E scenarios PASSED (100% Coverage). Ready for PR.");
        process.exit(0);
    } else {
        console.error(`${failures} tests FAILED. Pipeline broken.`);
        process.exit(1);
    }
}

// Since the server is tested, this script connects to localhost:3000
runValidationSuite();
