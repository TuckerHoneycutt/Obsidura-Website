from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[1]

def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())

def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    return yaml.safe_load(text[3:end]) or {}

def skill_dirs() -> list[Path]:
    root = REPO / "skills"
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if (p / "SKILL.md").exists())
