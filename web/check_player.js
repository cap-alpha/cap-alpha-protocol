require('dotenv').config({ path: '.env.local' });
const { BigQuery } = require('@google-cloud/bigquery');
const bq = new BigQuery({
  projectId: process.env.GCP_PROJECT_ID || 'my-project-1525668581184',
  credentials: process.env.GCP_CLIENT_EMAIL && process.env.GCP_PRIVATE_KEY ? {
    client_email: process.env.GCP_CLIENT_EMAIL,
    private_key: process.env.GCP_PRIVATE_KEY.replace(/\\n/g, '\n'),
  } : undefined,
});
async function run() {
  const query = `SELECT player_name, year, cap_hit_millions, team FROM \`nfl_dead_money.fact_player_efficiency\` WHERE player_name LIKE '%Kelce%' OR player_name LIKE '%Prescott%' OR player_name = 'Travis Kelce' ORDER BY year DESC LIMIT 15`;
  const [job] = await bq.createQueryJob({ query: query });
  const [rows] = await job.getQueryResults();
  console.log('BQ Results:', rows);
}
run().catch(console.error);
