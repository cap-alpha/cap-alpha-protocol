const { BigQuery } = require('@google-cloud/bigquery');
require('dotenv').config({ path: '.env.local' });

const bigquery = new BigQuery({
  projectId: process.env.GCP_PROJECT_ID,
  credentials: {
    client_email: process.env.GCP_CLIENT_EMAIL,
    private_key: process.env.GCP_PRIVATE_KEY.replace(/\\n/g, '\n'),
  }
});

async function run() {
  const players = ['Damar Hamlin', 'Zach Wilson', 'Taron Johnson'];
  for (const player of players) {
    console.log(`\n--- Querying BigQuery for ${player} ---`);
    const query = `SELECT * FROM \`my-project-1525668581184.nfl_dead_money.fact_player_efficiency\` WHERE player_name = '${player}' ORDER BY year DESC LIMIT 1`;
    try {
      const [rows] = await bigquery.query({ query });
      console.log(JSON.stringify(rows, null, 2));
    } catch (e) {
      console.error(`Error querying ${player}:`, e.message);
    }
  }
}
run();
