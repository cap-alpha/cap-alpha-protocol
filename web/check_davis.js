const fs = require('fs');

async function check() {
    try {
        const res = await fetch('http://localhost:3001/api/search'); // wait, there is no api.
        // Let's just use duckdb if we can, or read from wherever mock was.
        // Wait, getRosterData was querying motherduck.
    } catch(e) {
        console.error(e);
    }
}
check();
