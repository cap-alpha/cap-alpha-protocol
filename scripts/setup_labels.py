
import subprocess

LABELS = [
    {"name": "infrastructure", "color": "c5def5", "description": "Backend and DevOps tasks"},
    {"name": "backend", "color": "ededed", "description": "Server-side logic"},
    {"name": "critical-path", "color": "b60205", "description": "Blocks release"},
    {"name": "developer-experience", "color": "fbca04", "description": "Tooling and DX"},
    {"name": "feature", "color": "a2eeef", "description": "New functionality"},
    {"name": "authentication", "color": "d4c5f9", "description": "Clerk and Auth"},
    {"name": "product", "color": "0e8a16", "description": "Product requirements"},
    {"name": "monetization", "color": "006b75", "description": "Revenue generating features"},
    {"name": "ux", "color": "d93f0b", "description": "User Experience"},
    {"name": "onboarding", "color": "5319e7", "description": "New user flow"},
    {"name": "friction", "color": "e99695", "description": "Stops users from converting"},
    {"name": "navigation", "color": "0052cc", "description": "Menu and search"},
    {"name": "critical", "color": "b60205", "description": "Urgent"},
    {"name": "data", "color": "bfd4f2", "description": "Data pipeline"},
    {"name": "ingestion", "color": "f9d0c4", "description": "ETL tasks"},
    {"name": "ui", "color": "d4c5f9", "description": "Visual design"},
    {"name": "data-viz", "color": "c2e0c6", "description": "Charts and graphs"},
    {"name": "trust", "color": "006b75", "description": "Credibility issues"},
    {"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
    {"name": "polish", "color": "fef2c0", "description": "Fit and finish"},
    {"name": "strategy", "color": "6f42c1", "description": "High level planning"}
]

def create_labels():
    for label in LABELS:
        cmd = [
            "gh", "label", "create", label["name"],
            "--color", label["color"],
            "--description", label["description"],
            "--force"
        ]
        try:
            subprocess.run(cmd, check=False, capture_output=True) # Force ignores if exists
            print(f"Ensured label: {label['name']}")
        except Exception as e:
            print(f"Error label: {label['name']} - {e}")

if __name__ == "__main__":
    create_labels()
