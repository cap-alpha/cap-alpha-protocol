import os
import urllib.request
import ssl


def run():
    # Stable ESPN CDN URLs (Standard for analytics/dev use)
    logos = {
        "ARI": "https://a.espncdn.com/i/teamlogos/nfl/500/ari.png",
        "ATL": "https://a.espncdn.com/i/teamlogos/nfl/500/atl.png",
        "BAL": "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png",
        "BUF": "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png",
        "CAR": "https://a.espncdn.com/i/teamlogos/nfl/500/car.png",
        "CHI": "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png",
        "CIN": "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png",
        "CLE": "https://a.espncdn.com/i/teamlogos/nfl/500/cle.png",
        "DAL": "https://a.espncdn.com/i/teamlogos/nfl/500/dal.png",
        "DEN": "https://a.espncdn.com/i/teamlogos/nfl/500/den.png",
        "DET": "https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
        "GB": "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
        "HOU": "https://a.espncdn.com/i/teamlogos/nfl/500/hou.png",
        "IND": "https://a.espncdn.com/i/teamlogos/nfl/500/ind.png",
        "JAX": "https://a.espncdn.com/i/teamlogos/nfl/500/jax.png",
        "KC": "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png",
        "LAC": "https://a.espncdn.com/i/teamlogos/nfl/500/lac.png",
        "LAR": "https://a.espncdn.com/i/teamlogos/nfl/500/lar.png",
        "LV": "https://a.espncdn.com/i/teamlogos/nfl/500/lv.png",
        "MIA": "https://a.espncdn.com/i/teamlogos/nfl/500/mia.png",
        "MIN": "https://a.espncdn.com/i/teamlogos/nfl/500/min.png",
        "NE": "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png",
        "NO": "https://a.espncdn.com/i/teamlogos/nfl/500/no.png",
        "NYG": "https://a.espncdn.com/i/teamlogos/nfl/500/nyg.png",
        "NYJ": "https://a.espncdn.com/i/teamlogos/nfl/500/nyj.png",
        "PHI": "https://a.espncdn.com/i/teamlogos/nfl/500/phi.png",
        "PIT": "https://a.espncdn.com/i/teamlogos/nfl/500/pit.png",
        "SEA": "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png",
        "SF": "https://a.espncdn.com/i/teamlogos/nfl/500/sf.png",
        "TB": "https://a.espncdn.com/i/teamlogos/nfl/500/tb.png",
        "TEN": "https://a.espncdn.com/i/teamlogos/nfl/500/ten.png",
        "WAS": "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png",
    }

    out_dir = "data_raw/logos"
    os.makedirs(out_dir, exist_ok=True)

    # Bypass SSL context for simple script usage if needed
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for team, url in logos.items():
        fname = f"{out_dir}/{team}.png"
        if os.path.exists(fname):
            print(f"Skipping {team} (already exists)")
            continue

        print(f"Fetching {team} logo...")
        try:
            # Fake a user agent to avoid Wikipedia blocking
            req = urllib.request.Request(
                url,
                data=None,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
                },
            )

            with (
                urllib.request.urlopen(req, context=ctx) as response,
                open(f"{out_dir}/{team}.png", "wb") as out_file,
            ):
                data = response.read()
                out_file.write(data)
                print(f"Saved {team}.png ({len(data)} bytes)")

        except Exception as e:
            print(f"Error fetching {team}: {e}")


if __name__ == "__main__":
    run()
