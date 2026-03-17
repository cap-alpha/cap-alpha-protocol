export const NFL_CONFERENCES = {
    AFC: ["BAL", "BUF", "CIN", "CLE", "DEN", "HOU", "IND", "JAX", "KC", "LAC", "LV", "MIA", "NE", "NYJ", "PIT", "TEN"],
    NFC: ["ARI", "ATL", "CAR", "CHI", "DAL", "DET", "GB", "LAR", "MIN", "NO", "NYG", "PHI", "SEA", "SF", "TB", "WAS"]
};

export const TEAM_TO_CONFERENCE: Record<string, "AFC" | "NFC"> = {};

// Build reverse map
Object.entries(NFL_CONFERENCES).forEach(([conf, teams]) => {
    teams.forEach(team => {
        TEAM_TO_CONFERENCE[team] = conf as "AFC" | "NFC";
    });
});
