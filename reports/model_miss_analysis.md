# Cap Alpha Model Miss Analysis 
This diagnostic report details the worst prediction misses from the XGBoost Walk-Forward validation, sorting them into clear categories for manual review and architecture tuning.

## Top 50 False Positives (Model Called 'Bust', Player Was 'Safe')
These are players the ML model identified as toxic or high-risk, but who ultimately generated minimal dead money or performed well. 
*Diagnostic check: Is the model over-weighing injury history? Is it failing to understand cheap QB extensions?*

| player_name      |   year |   week | team   |   predicted |   actual |   delta |
|:-----------------|-------:|-------:|:-------|------------:|---------:|--------:|
| Kirk Cousins     |   2024 |      5 | ATL    |        6.1  |     0.58 |   -5.52 |
| Kirk Cousins     |   2024 |      8 | ATL    |        5.6  |     1.36 |   -4.24 |
| Tua Tagovailoa   |   2024 |     12 | MIA    |        5.7  |     1.47 |   -4.23 |
| Jared Goff       |   2024 |     15 | DET    |        5.1  |     1.26 |   -3.84 |
| Aidan Hutchinson |   2024 |      2 | DET    |        3.71 |     0    |   -3.71 |
| Tee Higgins      |   2024 |     17 | CIN    |        3.62 |     0    |   -3.62 |
| Jared Goff       |   2024 |     11 | DET    |        5.85 |     2.24 |   -3.6  |
| Tua Tagovailoa   |   2024 |     11 | MIA    |        5.68 |     2.28 |   -3.39 |
| Kyler Murray     |   2024 |     10 | ARI    |        6.12 |     2.88 |   -3.24 |
| Tee Higgins      |   2024 |      5 | CIN    |        3.25 |     0.03 |   -3.23 |
| Kyler Murray     |   2024 |      2 | ARI    |        5.96 |     2.75 |   -3.22 |
| Kyler Murray     |   2024 |     18 | ARI    |        5.41 |     2.25 |   -3.17 |
| Nik Bonitto      |   2024 |     13 | DEN    |        3.61 |     0.46 |   -3.16 |
| Tee Higgins      |   2024 |     11 | CIN    |        3.61 |     0.51 |   -3.09 |
| Kirk Cousins     |   2024 |      2 | ATL    |        5.96 |     2.99 |   -2.97 |
| Jalen Hurts      |   2024 |     10 | PHI    |        5.6  |     2.66 |   -2.94 |
| Nik Bonitto      |   2024 |     10 | DEN    |        4.33 |     1.46 |   -2.87 |
| Tee Higgins      |   2024 |     15 | CIN    |        3.58 |     0.73 |   -2.86 |
| Lamar Jackson    |   2024 |     15 | BAL    |        5.86 |     3.06 |   -2.79 |
| Nik Bonitto      |   2024 |     18 | DEN    |        3.45 |     0.66 |   -2.79 |
| Garrett Wilson   |   2024 |      9 | NYJ    |        3.4  |     0.63 |   -2.77 |
| Josh Allen       |   2024 |     14 | BUF    |        5.53 |     2.8  |   -2.73 |
| Matthew Stafford |   2024 |      8 | LAR    |        2.68 |     0    |   -2.68 |
| Kirk Cousins     |   2024 |      9 | ATL    |        5.01 |     2.37 |   -2.63 |
| Jalen Hurts      |   2024 |      8 | PHI    |        5.24 |     2.61 |   -2.63 |
| Tua Tagovailoa   |   2024 |     13 | MIA    |        5.31 |     2.71 |   -2.6  |
| Matthew Stafford |   2024 |     12 | LAR    |        2.6  |     0    |   -2.6  |
| Joe Burrow       |   2024 |      5 | CIN    |        6.19 |     3.6  |   -2.59 |
| Josh Allen       |   2018 |     17 | BUF    |        6.48 |     3.9  |   -2.58 |
| Tua Tagovailoa   |   2024 |      2 | MIA    |        6.74 |     4.18 |   -2.56 |
| D.J. Moore       |   2024 |      5 | CHI    |        3.3  |     0.75 |   -2.55 |
| Jared Goff       |   2024 |      4 | DET    |        5.98 |     3.45 |   -2.52 |
| Matthew Stafford |   2024 |      9 | LAR    |        2.48 |     0    |   -2.48 |
| Garrett Wilson   |   2024 |      6 | NYJ    |        3.74 |     1.29 |   -2.45 |
| Nik Bonitto      |   2024 |     11 | DEN    |        3.09 |     0.66 |   -2.44 |
| Tee Higgins      |   2024 |      7 | CIN    |        3.14 |     0.75 |   -2.39 |
| Matthew Stafford |   2024 |     14 | LAR    |        2.36 |     0    |   -2.36 |
| Garrett Wilson   |   2024 |     15 | NYJ    |        3.83 |     1.47 |   -2.35 |
| Jalen Hurts      |   2024 |     15 | PHI    |        5.46 |     3.1  |   -2.35 |
| Lamar Jackson    |   2024 |      7 | BAL    |        5.49 |     3.14 |   -2.34 |
| Tua Tagovailoa   |   2024 |     14 | MIA    |        5.18 |     2.84 |   -2.34 |
| Jared Goff       |   2024 |      6 | DET    |        5.7  |     3.37 |   -2.32 |
| Garrett Wilson   |   2024 |      5 | NYJ    |        3.63 |     1.31 |   -2.32 |
| Tee Higgins      |   2024 |     13 | CIN    |        3.07 |     0.8  |   -2.28 |
| Jalen Hurts      |   2024 |     14 | PHI    |        5.98 |     3.71 |   -2.27 |
| Myles Garrett    |   2018 |      3 | CLE    |        5.87 |     3.62 |   -2.24 |
| Zach Allen       |   2024 |     17 | DEN    |        2.23 |     0    |   -2.23 |
| Garrett Wilson   |   2018 |    nan | NYJ    |        4.61 |     2.4  |   -2.21 |
| Matthew Stafford |   2024 |     13 | LAR    |        2.45 |     0.24 |   -2.21 |
| Patrick Mahomes  |   2018 |    nan | KC     |        5.88 |     3.71 |   -2.17 |

## Top 50 False Negatives (Model Called 'Safe', Player Was 'Bust')
These are players the ML model believed were stable, highly-efficient assets extending their prime, but who catastrophicly failed and generated massive dead money liability.
*Diagnostic check: Were these isolated ACL tears? Or is the model completely missing a common degradation cliff (e.g. RBs after age 28)?*

| player_name     |   year |   week | team   |   predicted |   actual |   delta |
|:----------------|-------:|-------:|:-------|------------:|---------:|--------:|
| Deshaun Watson  |   2024 |      7 | CLE    |        7.37 |    13.07 |    5.7  |
| Deshaun Watson  |   2018 |    nan | CLE    |        8.72 |    13.53 |    4.81 |
| Deshaun Watson  |   2024 |      6 | CLE    |        8.09 |    12.86 |    4.78 |
| Deshaun Watson  |   2024 |      1 | CLE    |        7.76 |    12.06 |    4.3  |
| Deshaun Watson  |   2024 |      4 | CLE    |        8.12 |    12.06 |    3.94 |
| Deshaun Watson  |   2024 |      5 | CLE    |        8.41 |    12.31 |    3.9  |
| Deshaun Watson  |   2024 |      3 | CLE    |        7.58 |    11.29 |    3.71 |
| Deshaun Watson  |   2024 |      2 | CLE    |        8.38 |    12.07 |    3.69 |
| Deshaun Watson  |   2025 |    nan | CLE    |       10.29 |    13.53 |    3.24 |
| Micah Parsons   |   2024 |    nan | GB     |        4.25 |     7.24 |    2.99 |
| Dak Prescott    |   2025 |    nan | DAL    |        4.61 |     7.59 |    2.98 |
| Trevor Lawrence |   2024 |     13 | JAX    |        5.27 |     8.18 |    2.91 |
| Josh Allen      |   2018 |      6 | BUF    |        5.44 |     8.27 |    2.84 |
| Joe Burrow      |   2025 |    nan | CIN    |        6.05 |     8.62 |    2.57 |
| T.J. Watt       |   2024 |     17 | PIT    |        3.83 |     6.35 |    2.52 |
| Josh Allen      |   2024 |      4 | BUF    |        5.54 |     7.92 |    2.38 |
| Lamar Jackson   |   2025 |    nan | BAL    |        5.64 |     7.94 |    2.31 |
| Josh Allen      |   2025 |    nan | BUF    |        6.37 |     8.65 |    2.28 |
| Jared Goff      |   2025 |    nan | DET    |        4.46 |     6.68 |    2.22 |
| Lamar Jackson   |   2018 |      5 | BAL    |        5.69 |     7.91 |    2.21 |
| T.J. Watt       |   2024 |     10 | PIT    |        4.16 |     6.35 |    2.19 |
| Josh Allen      |   2024 |      2 | BUF    |        5.28 |     7.42 |    2.14 |
| Joe Burrow      |   2018 |    nan | CIN    |        6.48 |     8.62 |    2.14 |
| T.J. Watt       |   2018 |     14 | PIT    |        4.25 |     6.35 |    2.1  |
| Geno Smith      |   2024 |    nan | LV     |        1.35 |     3.44 |    2.09 |
| Danielle Hunter |   2024 |      9 | HOU    |        0.79 |     2.82 |    2.04 |
| Danielle Hunter |   2024 |     13 | HOU    |        0.81 |     2.82 |    2.01 |
| Trevor Lawrence |   2024 |      1 | JAX    |        5.01 |     7.02 |    2.01 |
| Danielle Hunter |   2024 |      5 | HOU    |        0.82 |     2.82 |    2.01 |
| Justin Herbert  |   2024 |     13 | LAC    |        5.33 |     7.33 |    2    |
| T.J. Watt       |   2024 |     14 | PIT    |        4.36 |     6.35 |    1.99 |
| T.J. Watt       |   2024 |     12 | PIT    |        4.37 |     6.35 |    1.99 |
| Danielle Hunter |   2024 |     10 | HOU    |        0.84 |     2.82 |    1.99 |
| Joe Burrow      |   2024 |      1 | CIN    |        5.99 |     7.97 |    1.98 |
| Danielle Hunter |   2024 |      4 | HOU    |        0.84 |     2.82 |    1.98 |
| T.J. Watt       |   2024 |      4 | PIT    |        4.41 |     6.35 |    1.95 |
| Jayden Daniels  |   2024 |      7 | WAS    |        0.08 |     2.02 |    1.93 |
| T.J. Watt       |   2024 |      7 | PIT    |        4.42 |     6.35 |    1.93 |
| Danielle Hunter |   2024 |      1 | HOU    |        0.9  |     2.82 |    1.93 |
| Bryce Young     |   2024 |      5 | CAR    |        0.09 |     2    |    1.91 |
| Danielle Hunter |   2024 |     17 | HOU    |        0.94 |     2.82 |    1.89 |
| T.J. Watt       |   2024 |      3 | PIT    |        3.69 |     5.55 |    1.86 |
| Jayden Daniels  |   2024 |     18 | WAS    |        0.13 |     1.99 |    1.86 |
| Danielle Hunter |   2024 |      3 | HOU    |        0.98 |     2.82 |    1.84 |
| Bryce Young     |   2024 |      2 | CAR    |        0.11 |     1.91 |    1.8  |
| Lamar Jackson   |   2018 |      3 | BAL    |        6.15 |     7.94 |    1.79 |
| T.J. Watt       |   2024 |     11 | PIT    |        3.8  |     5.55 |    1.75 |
| Lamar Jackson   |   2018 |      2 | BAL    |        6.18 |     7.92 |    1.74 |
| Trevor Lawrence |   2024 |      2 | JAX    |        5.66 |     7.4  |    1.74 |
| Trevor Lawrence |   2024 |      3 | JAX    |        5.25 |     6.98 |    1.73 |
