import re

# Each role: must-have skills (weighted higher) and nice-to-have skills.
ROLES = {
    "Python Developer": {
        "must": ["python", "flask", "django", "rest", "api", "sql", "git", "oop", "testing"],
        "nice": ["fastapi", "docker", "postgresql", "mongodb", "redis", "aws", "linux", "ci/cd", "pytest"],
    },
    "Machine Learning Engineer": {
        "must": ["python", "machine learning", "scikit-learn", "pandas", "numpy", "tensorflow", "pytorch", "model", "data"],
        "nice": ["deep learning", "nlp", "computer vision", "mlops", "docker", "sql", "feature engineering", "deployment", "aws"],
    },
    "Generative AI Engineer": {
        "must": ["python", "llm", "prompt", "langchain", "rag", "embeddings", "transformers", "api", "vector"],
        "nice": ["langgraph", "fine-tuning", "openai", "huggingface", "faiss", "chroma", "agents", "fastapi", "docker"],
    },
    "Data Analyst": {
        "must": ["sql", "excel", "python", "pandas", "visualization", "dashboard", "statistics", "analysis"],
        "nice": ["power bi", "tableau", "matplotlib", "seaborn", "a/b testing", "etl", "reporting", "looker"],
    },
    "Full-Stack Developer": {
        "must": ["html", "css", "javascript", "react", "node", "api", "database", "git", "responsive"],
        "nice": ["typescript", "mongodb", "sql", "docker", "rest", "tailwind", "next.js", "aws", "testing"],
    },
    "Frontend Developer": {
        "must": ["html", "css", "javascript", "react", "responsive", "git", "api", "accessibility"],
        "nice": ["typescript", "tailwind", "next.js", "redux", "testing", "figma", "performance", "webpack"],
    },
    "DevOps Engineer": {
        "must": ["linux", "docker", "kubernetes", "ci/cd", "git", "aws", "monitoring", "scripting"],
        "nice": ["terraform", "ansible", "jenkins", "github actions", "prometheus", "grafana", "python", "bash"],
    },
}

SECTIONS = {
    "Contact info": [r"@", r"\+?\d[\d\s\-]{8,}", r"linkedin|github"],
    "Summary / Objective": [r"summary", r"objective", r"profile", r"about me"],
    "Education": [r"education", r"b\.?tech", r"bachelor", r"university|college"],
    "Skills": [r"skills", r"technologies", r"tech stack"],
    "Projects": [r"projects?"],
    "Experience / Internships": [r"experience", r"internship", r"work history", r"open[- ]source"],
}

ACTION_VERBS = ["built", "developed", "designed", "implemented", "created", "led", "optimized",
                "improved", "deployed", "automated", "launched", "analyzed", "integrated",
                "reduced", "increased", "contributed", "engineered", "architected"]
WEAK = ["responsible for", "worked on", "helped with", "familiar with", "hardworking", "team player"]


def _has(text, kw):
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text) is not None


def analyze(text, role):
    low = text.lower()
    cfg = ROLES[role]
    words = len(re.findall(r"\w+", text))

    must_hit = [k for k in cfg["must"] if _has(low, k)]
    nice_hit = [k for k in cfg["nice"] if _has(low, k)]
    must_miss = [k for k in cfg["must"] if k not in must_hit]
    nice_miss = [k for k in cfg["nice"] if k not in nice_hit]
    kw_score = 35 * len(must_hit) / len(cfg["must"]) + 15 * len(nice_hit) / len(cfg["nice"])

    found = {}
    for name, pats in SECTIONS.items():
        found[name] = (sum(bool(re.search(p, low)) for p in pats) >= 2) if name == "Contact info" \
            else any(re.search(p, low) for p in pats)
    sec_score = 20 * sum(found.values()) / len(found)

    metrics = re.findall(r"\d+(?:\.\d+)?\s?(?:%|x|k\b|\+|users|ms|hours|projects|stars|prs)", low)
    metric_score = min(len(metrics), 5) / 5 * 15

    verbs = [v for v in ACTION_VERBS if _has(low, v)]
    verb_score = min(len(verbs), 8) / 8 * 10
    weak = [w for w in WEAK if w in low]

    if 300 <= words <= 800:
        len_score = 5
    elif 150 <= words < 300 or 800 < words <= 1000:
        len_score = 3
    else:
        len_score = 1
    total = round(kw_score + sec_score + metric_score + verb_score + len_score)

    tips = []
    if must_miss:
        tips.append(f"Add or demonstrate these core {role} skills if you have them: {', '.join(must_miss)}.")
    if nice_miss[:4]:
        tips.append(f"Bonus skills that would strengthen your profile: {', '.join(nice_miss[:4])}.")
    for name, ok in found.items():
        if not ok:
            tips.append(f"Missing section: {name}.")
    if len(metrics) < 3:
        tips.append("Quantify your impact (e.g. 'reduced load time by 40%', 'served 500+ users'). Aim for 3+ numbers.")
    if len(verbs) < 5:
        tips.append("Start bullet points with strong action verbs like built, deployed, optimized, automated.")
    if weak:
        tips.append(f"Replace weak phrases ({', '.join(weak)}) with specific achievements.")
    if words < 300:
        tips.append("Your resume looks short. Add project details, tech used, and outcomes.")
    elif words > 1000:
        tips.append("Your resume is long. Keep it to one page for fresher roles.")
    if not tips:
        tips.append("Strong resume. Tailor the summary to each job description before applying.")

    label = "Excellent fit" if total >= 80 else "Good, needs polish" if total >= 60 else "Needs work" if total >= 40 else "Weak match"
    return {
        "role": role, "score": min(total, 100), "label": label, "words": words,
        "breakdown": [
            {"name": "Role keywords", "got": round(kw_score), "max": 50},
            {"name": "Resume sections", "got": round(sec_score), "max": 20},
            {"name": "Measurable impact", "got": round(metric_score), "max": 15},
            {"name": "Action verbs", "got": round(verb_score), "max": 10},
            {"name": "Length", "got": len_score, "max": 5},
        ],
        "matched": must_hit + nice_hit, "missing": must_miss + nice_miss,
        "sections": found, "tips": tips,
    }
