const { BigQuery } = require('@google-cloud/bigquery');
const fs = require('fs');

const envFile = fs.readFileSync('.env.local', 'utf8');
const env = {};
envFile.split('\n').forEach(line => {
  const [key, ...ver] = line.split('=');
  if (key && ver) env[key] = ver.join('=').replace(/^"|"$/g, '');
});

const bigquery = new BigQuery({
  projectId: env.GCP_PROJECT_ID,
  credentials: {
    client_email: env.GCP_CLIENT_EMAIL,
    private_key: env.GCP_PRIVATE_KEY ? env.GCP_PRIVATE_KEY.replace(/\\n/g, '\n') : '',
  }
});

async function run() {
  const query = `SELECT * FROM \`${env.GCP_PROJECT_ID}.nfl_dead_money.fact_player_efficiency\` WHERE player_name = 'Deshaun Watson' ORDER BY year DESC LIMIT 1`;
  const [rows] = await bigquery.query({ query });
  console.log(JSON.stringify(rows[0], null, 2));
}

run();
