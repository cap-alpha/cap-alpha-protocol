import { getRosterData } from './app/actions';

async function test() {
    const roster = await getRosterData();
    const davis = roster.find(p => p.player_name === 'Gabriel Davis');
    console.log("ROSTER SIZE:", roster.length);
    console.log("GABRIEL DAVIS FOUND?", !!davis);
    if (davis) console.log(davis);
}

test();
