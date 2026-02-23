# Cap Alpha Model Miss Analysis 
This diagnostic report details the worst prediction misses from the XGBoost Walk-Forward validation, sorting them into clear categories for manual review and architecture tuning.

## Top 50 False Positives (Model Called 'Bust', Player Was 'Safe')
These are players the ML model identified as toxic or high-risk, but who ultimately generated minimal dead money or performed well. 
*Diagnostic check: Is the model over-weighing injury history? Is it failing to understand cheap QB extensions?*

| player_name         |   year | team   |   predicted |   actual |   delta |
|:--------------------|-------:|:-------|------------:|---------:|--------:|
| Aidan Hutchinson    |   2024 | DET    |       90.78 |    55.48 |  -35.3  |
| Aaron Rodgers       |   2023 | GB     |       27.82 |     0    |  -27.82 |
| Matt Ryan           |   2022 | ATL    |       27.46 |     0    |  -27.46 |
| Patrick Mahomes     |   2024 | KC     |       87.08 |    63.08 |  -24    |
| Tom Brady           |   2023 | TB     |       23.52 |     0    |  -23.52 |
| Deommodore Lenoir   |   2024 | SF     |       39.14 |    15.86 |  -23.28 |
| Bradley Chubb       |   2024 | MIA    |       29.91 |     8.7  |  -21.21 |
| Teair Tart          |   2024 | LAC    |       18.85 |     0    |  -18.85 |
| Kirk Cousins        |   2024 | ATL    |      108.84 |    90    |  -18.84 |
| Trey Hendrickson    |   2024 | CIN    |       18.48 |     0    |  -18.48 |
| Ryan Tannehill      |   2022 | TEN    |       28.46 |    10    |  -18.46 |
| Jared Goff          |   2022 | DET    |       18.42 |     0    |  -18.42 |
| Patrick Mahomes     |   2022 | KC     |       22.19 |     4    |  -18.19 |
| Russell Wilson      |   2022 | SEA    |       17.61 |     0    |  -17.61 |
| Garrett Wilson      |   2024 | NYJ    |       58.11 |    40.73 |  -17.38 |
| Leonard Williams    |   2023 | NYG    |       16.46 |     0    |  -16.46 |
| Chris Jones         |   2022 | KC     |       16.22 |     0    |  -16.22 |
| Brian O'Neill       |   2024 | MIN    |       38.54 |    22.63 |  -15.92 |
| Carson Wentz        |   2022 | WAS    |       15.62 |     0    |  -15.62 |
| Jack Conklin        |   2024 | CLE    |       30.9  |    15.32 |  -15.58 |
| Jared Goff          |   2023 | DET    |       14.55 |     0    |  -14.55 |
| Mike Evans          |   2023 | TB     |       14.27 |     0    |  -14.27 |
| Logan Wilson        |   2024 | DAL    |       24.04 |    10    |  -14.04 |
| Amari Cooper        |   2023 | CLE    |       13.65 |     0    |  -13.65 |
| Alex Highsmith      |   2024 | PIT    |       30.54 |    17.01 |  -13.53 |
| Quentin Lake        |   2024 | LAR    |       22.04 |     8.69 |  -13.35 |
| Garett Bolles       |   2024 | DEN    |       37    |    23.74 |  -13.27 |
| Taysom Hill         |   2024 | NO     |       23.32 |    10.1  |  -13.22 |
| Lamar Jackson       |   2022 | BAL    |       12.9  |     0    |  -12.9  |
| Brandin Cooks       |   2023 | HOU    |       12.81 |     0    |  -12.81 |
| Kevin Dotson        |   2024 | LAR    |       23.72 |    11.25 |  -12.47 |
| Kerby Joseph        |   2024 | DET    |       36.75 |    24.38 |  -12.37 |
| Christian McCaffrey |   2023 | CAR    |       12.33 |     0    |  -12.33 |
| Luke Wattenberg     |   2024 | DEN    |       25.56 |    13.29 |  -12.27 |
| Wyatt Teller        |   2024 | CLE    |       28.86 |    16.59 |  -12.27 |
| Pat Freiermuth      |   2024 | PIT    |       23.79 |    11.6  |  -12.19 |
| Abraham Lucas       |   2024 | SEA    |       24.97 |    12.79 |  -12.18 |
| Deshaun Watson      |   2022 | HOU    |       12.12 |     0    |  -12.12 |
| Vita Vea            |   2024 | TB     |       26.85 |    14.73 |  -12.11 |
| Ryan Tannehill      |   2023 | TEN    |       22.09 |    10    |  -12.09 |
| Terrel Bernard      |   2024 | BUF    |       26.17 |    14.1  |  -12.07 |
| Jonathon Cooper     |   2024 | DEN    |       29.53 |    17.61 |  -11.92 |
| Alim McNeill        |   2024 | DET    |       39.92 |    28.06 |  -11.86 |
| Austin Jackson      |   2024 | MIA    |       24.48 |    13.07 |  -11.41 |
| Jalen Ramsey        |   2023 | LAR    |       11.37 |     0    |  -11.37 |
| Julio Jones         |   2022 | ATL    |       11.34 |     0    |  -11.34 |
| Chris Jones         |   2024 | KC     |       71.3  |    60    |  -11.3  |
| Budda Baker         |   2024 | ARI    |       28.67 |    17.44 |  -11.23 |
| Robert Quinn        |   2022 | CHI    |       11.2  |     0    |  -11.2  |
| Khalil Mack         |   2022 | CHI    |       11.11 |     0    |  -11.11 |

## Top 50 False Negatives (Model Called 'Safe', Player Was 'Bust')
These are players the ML model believed were stable, highly-efficient assets extending their prime, but who catastrophicly failed and generated massive dead money liability.
*Diagnostic check: Were these isolated ACL tears? Or is the model completely missing a common degradation cliff (e.g. RBs after age 28)?*

| player_name                      |   year | team   |   predicted |   actual |   delta |
|:---------------------------------|-------:|:-------|------------:|---------:|--------:|
| Deshaun Watson                   |   2024 | CLE    |      144.38 |   230    |   85.62 |
| Micah Parsons                    |   2024 | GB     |       73.99 |   123.11 |   49.12 |
| Trevor Lawrence                  |   2024 | JAX    |       96.32 |   142    |   45.68 |
| Joe Burrow                       |   2024 | CIN    |      103.02 |   146.51 |   43.49 |
| Josh Allen                       |   2024 | BUF    |      104.04 |   147    |   42.96 |
| Justin Herbert                   |   2024 | LAC    |       98.24 |   133.74 |   35.49 |
| Aaron Rodgers                    |   2022 | GB     |       21.02 |    48.96 |   27.94 |
| Lamar Jackson                    |   2024 | BAL    |      107.06 |   135    |   27.94 |
| Danielle Hunter                  |   2024 | HOU    |       22.55 |    48    |   25.45 |
| Jared Goff                       |   2024 | DET    |       91.21 |   113.61 |   22.4  |
| Joe Burrow                       |   2023 | CIN    |        5.83 |    27.94 |   22.11 |
| Lamar Jackson                    |   2023 | BAL    |        8.03 |    29.3  |   21.27 |
| Cameron Ward                     |   2024 | TEN    |       28.06 |    48.84 |   20.78 |
| Will Campbell                    |   2024 | NE     |       23.63 |    43.66 |   20.03 |
| Chris Godwin                     |   2024 | TB     |       24.09 |    44    |   19.91 |
| Travis Hunter                    |   2024 | JAX    |       26.91 |    46.65 |   19.74 |
| Daron Payne                      |   2024 | WAS    |       36.24 |    55.01 |   18.77 |
| Andrew Thomas                    |   2024 | NYG    |       48.96 |    67    |   18.04 |
| Justin Jefferson                 |   2024 | MIN    |       70.7  |    88.74 |   18.04 |
| Aaron Donald                     |   2022 | LAR    |       14.76 |    32    |   17.24 |
| Geno Smith                       |   2024 | LV     |       41.59 |    58.5  |   16.91 |
| Tyreek Hill                      |   2024 | MIA    |       37.95 |    54    |   16.05 |
| Abdul Carter                     |   2024 | NYG    |       29.24 |    45.26 |   16.02 |
| A.J. Brown                       |   2024 | PHI    |       35.03 |    51    |   15.97 |
| T.J. Watt                        |   2024 | PIT    |       92.18 |   108    |   15.82 |
| Joe Alt                          |   2024 | LAC    |       17.41 |    33.16 |   15.75 |
| Matthew Stafford                 |   2022 | LAR    |        8.31 |    24    |   15.69 |
| Mason Graham                     |   2024 | CLE    |       25.61 |    40.87 |   15.26 |
| Armand Membou                    |   2024 | NYJ    |       17.15 |    31.91 |   14.76 |
| Anthony Richardson               |   2024 | IND    |       19.46 |    33.99 |   14.54 |
| Nick Bosa                        |   2023 | SF     |        5.5  |    20    |   14.5  |
| Tom Brady                        |   2022 | TB     |        7.24 |    21.55 |   14.31 |
| Ronnie Stanley                   |   2024 | BAL    |       29.8  |    44    |   14.2  |
| Jayden Daniels                   |   2024 | WAS    |       23.62 |    37.75 |   14.12 |
| Harrison Jr. Marvin Harrison Jr. |   2024 | ARI    |       21.57 |    35.37 |   13.81 |
| Caleb Williams                   |   2024 | CHI    |       25.68 |    39.49 |   13.8  |
| Preston Smith                    |   2022 | GB     |        5.67 |    19.38 |   13.71 |
| Maxx Crosby                      |   2024 | LV     |       48.8  |    62.5  |   13.7  |
| DeForest Buckner                 |   2024 | IND    |       29.67 |    43.25 |   13.58 |
| Kyle Pitts                       |   2024 | ATL    |       19.36 |    32.91 |   13.55 |
| Devon Witherspoon                |   2024 | SEA    |       18.41 |    31.86 |   13.45 |
| Rashawn Slater                   |   2024 | LAC    |       42.62 |    56    |   13.38 |
| Fred Warner                      |   2024 | SF     |       27.45 |    40.8  |   13.35 |
| Colston Loveland                 |   2024 | CHI    |       13.64 |    26.64 |   13    |
| Pittman Jr. Michael Pittman Jr.  |   2024 | IND    |       28.02 |    41    |   12.98 |
| Drake Maye                       |   2024 | NE     |       23.73 |    36.64 |   12.91 |
| Matthew Stafford                 |   2023 | LAR    |       11.31 |    24    |   12.69 |
| Travon Walker                    |   2024 | JAX    |       24.75 |    37.37 |   12.63 |
| Carlton Davis                    |   2024 | NE     |       21.98 |    34.5  |   12.52 |
| Uchenna Nwosu                    |   2023 | SEA    |        4.56 |    17    |   12.44 |
