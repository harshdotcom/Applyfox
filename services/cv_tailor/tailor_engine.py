#!/usr/bin/env python3
"""
tailor_engine.py - Core engine for analyzing Job Descriptions and precisely tailoring
the candidate's LaTeX CV (data/main.tex) across PROFILE, TECHNICAL SKILLS, and PROJECTS.
"""

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ==============================================================================
# Verified Skill Taxonomy for Harsh Jha
# ==============================================================================
CANDIDATE_SKILLS = {
    "languages": {
        "Python": ["python", "python3", "py"],
        "Go": ["go", "golang"],
        "TypeScript": ["typescript", "ts"],
        "JavaScript": ["javascript", "js", "es6"],
        "C++": ["c++", "cpp"],
        "SQL": ["sql"],
    },
    "ai_genai": {
        "LLMs": ["llm", "llms", "large language model", "large language models"],
        "AI Agents": ["ai agents", "agentic", "ai agent", "multi-agent", "agentic workflows"],
        "LangChain": ["langchain"],
        "LangGraph": ["langgraph"],
        "RAG": ["rag", "retrieval augmented generation", "retrieval-augmented"],
        "Prompt Engineering": ["prompt engineering", "few-shot", "cot"],
        "Tool Calling": ["tool calling", "function calling", "tools integration"],
        "Structured Outputs": ["structured output", "structured outputs", "pydantic parser"],
        "Vector Search": ["vector search", "vector database", "vector db", "vector stores", "embeddings"],
        "AI Workflow Automation": ["ai workflow automation", "ai automation", "intelligent automation"],
        "Agent Orchestration": ["agent orchestration", "stateful agents"],
        "Retrieval Pipelines": ["retrieval pipelines", "semantic search", "hybrid search"],
        "AI Evaluation": ["ai evaluation", "evals", "ragas"],
    },
    "backend": {
        "FastAPI": ["fastapi"],
        "Gin": ["gin", "gin-gonic"],
        "Fiber": ["fiber"],
        "Node.js": ["node.js", "nodejs", "node"],
        "Express.js": ["express.js", "express"],
        "REST APIs": ["rest", "rest api", "rest apis", "restful"],
        "gRPC": ["grpc", "protobuf", "protocol buffers"],
        "Microservices": ["microservices", "microservice", "service-oriented"],
        "API Gateway": ["api gateway"],
        "WebSockets": ["websocket", "websockets"],
    },
    "data": {
        "PostgreSQL": ["postgresql", "postgres"],
        "MongoDB": ["mongodb", "mongo"],
        "MySQL": ["mysql"],
        "SQL Server": ["sql server", "mssql"],
        "Redis": ["redis", "caching", "in-memory cache"],
        "Vector Databases": ["chroma", "pinecone", "qdrant", "weaviate", "faiss"],
    },
    "cloud": {
        "AWS": ["aws", "amazon web services"],
        "Azure": ["azure", "microsoft azure"],
        "AWS Bedrock": ["aws bedrock", "bedrock"],
        "AWS Textract": ["aws textract", "textract"],
        "Oracle Cloud Infrastructure": ["oracle cloud", "oci"],
        "S3": ["s3", "amazon s3"],
        "Lambda": ["lambda", "serverless"],
    },
    "devops": {
        "Docker": ["docker", "containerization", "containers"],
        "Kubernetes": ["kubernetes", "k8s"],
        "GitHub Actions": ["github actions", "gh actions"],
        "CI/CD": ["ci/cd", "ci cd", "continuous integration", "continuous deployment"],
        "Containerized Deployment": ["containerized deployment", "containerized"],
    },
    "architecture": {
        "System Design": ["system design", "systems design"],
        "Distributed Systems": ["distributed systems", "distributed architecture"],
        "Event-Driven Architecture": ["event-driven", "event driven", "pub/sub", "kafka", "message queues"],
        "Clean Architecture": ["clean architecture", "hexagonal"],
        "SOLID Principles": ["solid", "solid principles"],
        "High Concurrency": ["concurrency", "high concurrency", "goroutines", "asyncio", "multithreading"],
        "Scalability": ["scalability", "scalable backend", "performance optimization"],
    },
    "security": {
        "JWT": ["jwt", "json web token"],
        "RBAC": ["rbac", "role-based access control"],
        "API Validation": ["api validation", "input validation"],
        "Secure API Design": ["secure api design", "api security", "oauth", "oauth2"],
    },
}


@dataclass
class JDAnalysis:
    """Structured breakdown of extracted requirements from a Job Description."""
    raw_jd: str
    target_title: str
    archetype: str  # "AI_ENGINEER", "BACKEND_ENGINEER", "FULL_STACK", "DEVOPS", "GENERAL_SDE"
    matched_skills: Dict[str, List[str]]
    all_matched_skills: List[str]
    match_score: int  # 0 to 100 percentage
    top_priorities: List[str]
    missing_nice_to_haves: List[str]


def analyze_jd(jd_text: str, custom_title: Optional[str] = None) -> JDAnalysis:
    """Analyze a Job Description and extract key skills, role archetype, and priorities."""
    text_lower = jd_text.lower()
    matched: Dict[str, List[str]] = {cat: [] for cat in CANDIDATE_SKILLS}
    flat_matched: List[str] = []

    for cat, skills_dict in CANDIDATE_SKILLS.items():
        for canonical_name, aliases in skills_dict.items():
            for alias in aliases:
                # Use word boundary search for clean matching
                pattern = r"(?:\b|_)" + re.escape(alias) + r"(?:\b|_)"
                if re.search(pattern, text_lower):
                    if canonical_name not in matched[cat]:
                        matched[cat].append(canonical_name)
                    if canonical_name not in flat_matched:
                        flat_matched.append(canonical_name)
                    break

    # Determine role archetype
    ai_weight = len(matched["ai_genai"]) * 3
    backend_weight = len(matched["backend"]) * 2.5 + len(matched["data"]) * 1.5 + len(matched["languages"]) * 1.5
    devops_weight = len(matched["devops"]) * 2 + len(matched["cloud"]) * 1.5

    # Check for strong title indicators
    title = (custom_title or "").strip()
    if not title:
        # Try extracting title from JD first few lines
        first_lines = "\n".join(jd_text.splitlines()[:5]).lower()
        if "ai engineer" in first_lines or "llm engineer" in first_lines or "genai" in first_lines:
            title = "AI / GenAI Software Development Engineer"
        elif "backend" in first_lines or "go" in first_lines or "golang" in first_lines:
            title = "Backend Software Development Engineer"
        elif "full stack" in first_lines or "fullstack" in first_lines:
            title = "Full Stack Software Development Engineer"
        elif "cloud" in first_lines or "devops" in first_lines:
            title = "Cloud & Backend Software Development Engineer"
        else:
            title = "Software Development Engineer"

    title_lower = title.lower()
    if any(k in title_lower for k in ["ai", "genai", "llm", "agent", "machine learning"]):
        archetype = "AI_ENGINEER"
    elif any(k in title_lower for k in ["backend", "distributed", "systems", "go", "golang", "api"]):
        archetype = "BACKEND_ENGINEER"
    elif any(k in title_lower for k in ["full stack", "fullstack", "frontend"]):
        archetype = "FULL_STACK"
    elif any(k in title_lower for k in ["devops", "cloud", "infrastructure", "platform", "sre"]):
        archetype = "DEVOPS"
    elif ai_weight > backend_weight and ai_weight > devops_weight:
        archetype = "AI_ENGINEER"
    elif backend_weight >= ai_weight and backend_weight >= devops_weight:
        archetype = "BACKEND_ENGINEER"
    else:
        archetype = "GENERAL_SDE"

    # Compute a reasonable match score based on candidate coverage
    total_distinct_skills = sum(len(v) for v in CANDIDATE_SKILLS.values())
    match_score = min(98, max(45, int((len(flat_matched) / 12) * 100)))

    # Identify top priority skills
    priorities = []
    if archetype == "AI_ENGINEER":
        priorities = matched["ai_genai"] + matched["backend"][:3] + matched["languages"][:2]
    elif archetype == "BACKEND_ENGINEER":
        priorities = matched["backend"] + matched["languages"] + matched["data"][:3] + matched["architecture"][:2]
    elif archetype == "DEVOPS":
        priorities = matched["devops"] + matched["cloud"] + matched["backend"][:3]
    else:
        priorities = flat_matched[:8]

    # Deduplicate while preserving order
    top_priorities = []
    for p in priorities:
        if p not in top_priorities:
            top_priorities.append(p)

    return JDAnalysis(
        raw_jd=jd_text,
        target_title=title,
        archetype=archetype,
        matched_skills=matched,
        all_matched_skills=flat_matched,
        match_score=match_score,
        top_priorities=top_priorities[:8],
        missing_nice_to_haves=[]
    )


# ==============================================================================
# LaTeX Helpers
# ==============================================================================
def escape_latex(s: str) -> str:
    """Ensure standard LaTeX special characters are properly escaped."""
    # Do not double-escape if already escaped
    s = re.sub(r'(?<!\\)&', r'\&', s)
    s = re.sub(r'(?<!\\)%', r'\%', s)
    s = re.sub(r'(?<!\\)_', r'\_', s)
    return s


def reorder_list_with_priorities(full_list: List[str], prioritized: List[str]) -> List[str]:
    """Reorder a list of skills so prioritized items come first without losing any."""
    p_set = set(prioritized)
    first_part = [item for item in full_list if item in p_set]
    # Add any prioritized items that candidate has but weren't in that exact category default
    second_part = [item for item in full_list if item not in p_set]
    return first_part + second_part


# ==============================================================================
# Section Tailoring Implementations
# ==============================================================================
def build_tailored_profile(analysis: JDAnalysis) -> str:
    """Construct tailored PROFILE section based on role archetype and matched skills."""
    role_title = analysis.target_title
    archetype = analysis.archetype
    matched = analysis.matched_skills

    # 1. Headline bullet
    if archetype == "BACKEND_ENGINEER":
        langs = []
        if "Go" in matched["languages"]:
            langs.append("Go")
        if "Python" in matched["languages"]:
            langs.append("Python")
        if not langs:
            langs = ["Go", "Python"]
        lang_str = " and ".join(langs)

        b1 = (
            f"Backend-focused Software Development Engineer with \\textbf{{2.5 years of experience}} "
            f"building high-throughput {lang_str} backend systems, microservices, cloud-native services, "
            f"and production-grade software."
        )
        b2 = (
            "Hands-on expertise developing production \\textbf{REST APIs, gRPC services, and microservices} "
            "with PostgreSQL, Redis caching, structured data pipelines, and clean modular architecture."
        )
        b3 = (
            "Proven track record integrating \\textbf{LLM workflows, AI agents, and RAG pipelines} "
            "into backend business platforms using LangChain, LangGraph, and AWS Bedrock."
        )
        b4 = (
            "Open-source maintainer of \\textbf{VitaTrack.ai}, an AI-powered healthcare platform for "
            "medical document extraction, report summarization, health-record organization, and intelligent health-data workflows."
        )

    elif archetype == "AI_ENGINEER":
        b1 = (
            f"AI-focused Software Development Engineer with \\textbf{{2.5 years of experience}} "
            "building production-grade LLM applications, agentic AI workflows, scalable backend systems, "
            "and cloud-native microservices."
        )
        # Highlight specific AI techniques requested
        ai_terms = []
        if "LangGraph" in matched["ai_genai"]:
            ai_terms.append("LangGraph")
        if "LangChain" in matched["ai_genai"]:
            ai_terms.append("LangChain")
        if "RAG" in matched["ai_genai"]:
            ai_terms.append("RAG pipelines")
        if "Tool Calling" in matched["ai_genai"]:
            ai_terms.append("tool calling")
        if "Vector Search" in matched["ai_genai"]:
            ai_terms.append("vector search")
        if not ai_terms:
            ai_terms = ["LangChain", "LangGraph", "RAG", "tool calling", "structured outputs"]

        ai_str = ", ".join(ai_terms)
        b2 = (
            f"Hands-on experience designing and integrating \\textbf{{LLM and agentic AI workflows}} "
            f"using {ai_str}, AWS Bedrock, prompt engineering, and structured outputs."
        )
        b3 = (
            "Strong backend and systems foundation across \\textbf{Python, Go, TypeScript, REST APIs, "
            "PostgreSQL, Redis, Docker, Kubernetes, AWS, and Azure}, with experience taking features from design through production."
        )
        b4 = (
            "Open-source maintainer of \\textbf{VitaTrack.ai}, an AI-powered healthcare platform for "
            "medical document extraction, report summarization, health-record organization, and intelligent health-data workflows."
        )

    elif archetype == "DEVOPS":
        b1 = (
            f"Cloud & Systems Software Development Engineer with \\textbf{{2.5 years of experience}} "
            "architecting cloud-native microservices, containerized deployments, backend APIs, and distributed systems."
        )
        b2 = (
            "Deep experience with \\textbf{Docker, Kubernetes, AWS, Azure, GitHub Actions CI/CD pipelines, "
            "and containerized deployment}, ensuring high availability, observability, and smooth production releases."
        )
        b3 = (
            "Solid backend engineering foundation across \\textbf{Go, Python, REST APIs, PostgreSQL, Redis, "
            "and microservices}, alongside hands-on integration of LLMs and agentic AI workflows."
        )
        b4 = (
            "Open-source maintainer of \\textbf{VitaTrack.ai}, an AI-powered healthcare platform for "
            "medical document extraction, report summarization, health-record organization, and intelligent health-data workflows."
        )

    else:  # GENERAL_SDE / FULL_STACK
        b1 = (
            f"Software Development Engineer with \\textbf{{2.5 years of experience}} "
            "building backend systems, AI-powered applications, cloud-native services, microservices, and production-grade software."
        )
        b2 = (
            "Hands-on experience designing and integrating \\textbf{LLM and agentic AI workflows} "
            "using LangChain, LangGraph, RAG, tool calling, prompt engineering, structured outputs, AWS Bedrock, and AWS Textract."
        )
        b3 = (
            "Strong backend and systems foundation across \\textbf{Go, Python, TypeScript, REST APIs, "
            "PostgreSQL, MongoDB, Docker, Kubernetes, AWS, and Azure}, with experience taking features from design through production."
        )
        b4 = (
            "Open-source maintainer of \\textbf{VitaTrack.ai}, an AI-powered healthcare platform for "
            "medical document extraction, report summarization, health-record organization, and intelligent health-data workflows."
        )

    lines = [
        "%-----------PROFILE-----------",
        r"\section{\color{airforceblue}PROFILE}",
        r"\resumeItemListStart",
        "",
        rf"\resumeItem{{{b1}}}",
        "",
        rf"\resumeItem{{{b2}}}",
        "",
        rf"\resumeItem{{{b3}}}",
        "",
        rf"\resumeItem{{{b4}}}",
        "",
        r"\resumeItemListEnd",
        ""
    ]
    return "\n".join(lines)


def build_tailored_skills(analysis: JDAnalysis) -> str:
    """Construct tailored TECHNICAL SKILLS section prioritizing JD requirements."""
    archetype = analysis.archetype
    matched = analysis.matched_skills

    # Base dictionary of skills
    skills_cat: Dict[str, Tuple[str, List[str]]] = {
        "ai_genai": (
            "AI / GenAI",
            ["LLMs", "AI Agents", "Agentic AI", "LangChain", "LangGraph", "RAG", "Prompt Engineering", "Tool Calling", "Function Calling", "LLM Integration", "AI Workflow Automation"]
        ),
        "ai_eng": (
            "AI Engineering",
            ["Agent Orchestration", "Retrieval Pipelines", "Vector Search", "Embeddings", "Context Engineering", "Structured Outputs", "Model Integration", "AI Evaluation"]
        ),
        "programming": (
            "Programming",
            ["Python", "Go", "TypeScript", "JavaScript", "C++"]
        ),
        "backend": (
            "Backend",
            ["FastAPI", "Gin", "Fiber", "Node.js", "Express.js", "REST APIs", "gRPC", "Microservices", "API Gateway"]
        ),
        "data": (
            "Data",
            ["PostgreSQL", "MongoDB", "MySQL", "SQL Server", "Redis"]
        ),
        "cloud": (
            "Cloud \\& AI Services",
            ["AWS", "Azure", "AWS Bedrock", "AWS Textract", "Oracle Cloud Infrastructure"]
        ),
        "devops": (
            "DevOps \\& Infrastructure",
            ["Docker", "Kubernetes", "GitHub Actions", "CI/CD", "Containerized Deployment"]
        ),
        "architecture": (
            "Architecture",
            ["System Design", "Distributed Systems", "Event-Driven Architecture", "Microservices", "Clean Architecture", "SOLID Principles"]
        ),
        "security": (
            "Security",
            ["JWT", "RBAC", "API Validation", "Secure API Design"]
        ),
    }

    # Order categories according to archetype
    if archetype == "BACKEND_ENGINEER":
        category_order = ["programming", "backend", "architecture", "data", "devops", "cloud", "ai_genai", "security"]
    elif archetype == "AI_ENGINEER":
        category_order = ["ai_genai", "ai_eng", "programming", "backend", "data", "cloud", "devops", "architecture", "security"]
    elif archetype == "DEVOPS":
        category_order = ["devops", "cloud", "backend", "programming", "data", "architecture", "security", "ai_genai"]
    else:
        category_order = ["ai_genai", "ai_eng", "programming", "backend", "data", "cloud", "devops", "architecture", "security"]

    # Re-order skills within each category so matching items appear first
    items = []
    for cat_key in category_order:
        if cat_key not in skills_cat:
            continue
        title, skill_list = skills_cat[cat_key]

        # Find matching skills for this category
        matched_in_cat = matched.get(cat_key, [])
        if cat_key == "ai_eng":
            matched_in_cat = matched.get("ai_genai", [])

        # Reorder list with matched items first
        reordered = reorder_list_with_priorities(skill_list, matched_in_cat)
        skills_str = ", ".join(reordered)
        items.append(rf"\resumeItem{{\textbf{{{title}:}} {skills_str}}}")

    lines = [
        "%-----------TECHNICAL SKILLS-----------",
        r"\section{\color{airforceblue}TECHNICAL SKILLS}",
        r"\resumeItemListStart",
        ""
    ]
    for item in items:
        lines.append(item)
        lines.append("")
    lines.append(r"\resumeItemListEnd")
    lines.append("")
    return "\n".join(lines)


def build_tailored_projects(analysis: JDAnalysis) -> str:
    """Construct tailored PROJECTS section adjusting project headers and tech stack tags."""
    archetype = analysis.archetype
    matched = analysis.matched_skills

    # Project 1: VitaTrack.ai Tech Stack Subtitle
    # Default: "Go, Python, AWS, PostgreSQL"
    vt_tech = ["Go", "Python"]
    if "FastAPI" in matched["backend"]:
        vt_tech.append("FastAPI")
    if "PostgreSQL" in matched["data"] or not vt_tech:
        vt_tech.append("PostgreSQL")
    if "AWS Bedrock" in matched["cloud"] or "LLMs" in matched["ai_genai"]:
        vt_tech.append("AWS Bedrock")
    elif "AWS" in matched["cloud"]:
        vt_tech.append("AWS")
    if "Docker" in matched["devops"] and len(vt_tech) < 5:
        vt_tech.append("Docker")
    if "Microservices" in matched["backend"] and len(vt_tech) < 5:
        vt_tech.append("Microservices")

    # Keep to 4-5 items
    vt_tech_str = ", ".join(vt_tech[:5])

    # Project 2: AI Agent Workflow System Tech Stack Subtitle
    # Default: "Python, LangChain, LangGraph, LLMs"
    agent_tech = ["Python"]
    if "LangGraph" in matched["ai_genai"] or archetype == "AI_ENGINEER":
        agent_tech.append("LangGraph")
    if "LangChain" in matched["ai_genai"] or "LangChain" not in agent_tech:
        agent_tech.append("LangChain")
    if "RAG" in matched["ai_genai"]:
        agent_tech.append("RAG")
    if "Tool Calling" in matched["ai_genai"]:
        agent_tech.append("Tool Calling")
    elif "FastAPI" in matched["backend"] and len(agent_tech) < 4:
        agent_tech.append("FastAPI")
    elif "Vector Search" in matched["ai_genai"] and len(agent_tech) < 4:
        agent_tech.append("Vector Search")
    else:
        agent_tech.append("LLMs")

    agent_tech_str = ", ".join(agent_tech[:5])

    lines = [
        "%-----------PROJECTS-----------",
        r"\section{\color{airforceblue}PROJECTS}",
        r"\resumeSubHeadingListStart",
        "",
        "%----------VITATRACK----------",
        r"\resumeProjectHeading",
        rf"{{\textbf{{VitaTrack.ai -- AI Medical Report Platform}} $|$ {vt_tech_str}}}",
        r"{\href{https://github.com/harshdotcom/vitalTrack.ai-}{GitHub}}",
        "",
        r"\resumeItemListStart",
        "",
        r"\resumeItem{Developing an open-source AI healthcare platform for managing \textbf{medical reports, prescriptions, symptoms, medications, health records, and daily health notes}.}",
        "",
        r"\resumeItem{Built secure \textbf{Go backend APIs} and structured healthcare data workflows using \textbf{PostgreSQL} for medical record management.}",
        "",
        r"\resumeItem{Integrated \textbf{AWS Textract} to extract text and structured data from medical reports, prescriptions, and healthcare documents.}",
        "",
        r"\resumeItem{Integrated \textbf{AWS Bedrock and LLMs} with prompt engineering to summarize medical reports and transform unstructured health data into structured, actionable information.}",
        "",
        r"\resumeItem{Designed AI workflows for \textbf{medical document analysis, health-history tracking, report processing, and patient record organization}.}",
        "",
        r"\resumeItem{Built supporting \textbf{Angular} interfaces for document uploads, health logs, dashboards, and medical data management.}",
        "",
        r"\resumeItemListEnd",
        "",
        "",
        "%----------AI AGENT WORKFLOW----------",
        r"\resumeProjectHeading",
        rf"{{\textbf{{AI Agent Workflow System}} $|$ {agent_tech_str}}}",
        r"{\href{https://github.com/harshdotcom/naukriAuto.Ai}{GitHub}}",
        "",
        r"\resumeItemListStart",
        "",
        r"\resumeItem{Engineered multi-step \textbf{AI agent workflows} using Python, LangChain, LangGraph, and LLM APIs for intelligent automation and structured decision-making.}",
        "",
        r"\resumeItem{Designed stateful agent workflows for \textbf{document processing, summarization, API integration, tool execution, and structured response generation}.}",
        "",
        r"\resumeItem{Implemented \textbf{tool calling, prompt templates, reusable chains, memory, state management, and conditional workflow execution} for agent-driven automation.}",
        "",
        r"\resumeItem{Integrated AI agents with \textbf{REST APIs and external tools} to execute tasks, process information, and support real-world business workflows.}",
        "",
        r"\resumeItemListEnd",
        "",
        r"\resumeSubHeadingListEnd",
        ""
    ]
    return "\n".join(lines)


# ==============================================================================
# Master Tailor Function
# ==============================================================================
@dataclass
class TailoredCVResult:
    tailored_tex: str
    original_tex: str
    analysis: JDAnalysis
    profile_diff: str
    skills_diff: str
    projects_diff: str
    full_diff: str
    metadata: Dict[str, Any]


def tailor_cv(
    base_tex_path: Path,
    jd_text: str,
    company_name: str,
    job_title: Optional[str] = None,
    job_url: Optional[str] = None,
    referral_name: Optional[str] = None,
    referral_contact: Optional[str] = None,
) -> TailoredCVResult:
    """Read base main.tex, tailor PROFILE, TECHNICAL SKILLS, and PROJECTS, and return result."""
    original_tex = Path(base_tex_path).read_text(encoding="utf-8")

    # Analyze the JD
    analysis = analyze_jd(jd_text, custom_title=job_title)

    # Generate tailored sections
    new_profile = build_tailored_profile(analysis)
    new_skills = build_tailored_skills(analysis)
    new_projects = build_tailored_projects(analysis)

    # Replace PROFILE section
    profile_pattern = re.compile(r'(%-----------PROFILE-----------.*?)(?=%-----------EDUCATION-----------)', re.DOTALL)
    old_profile_match = profile_pattern.search(original_tex)
    old_profile = old_profile_match.group(1) if old_profile_match else ""
    tex_after_profile = profile_pattern.sub(lambda m: new_profile, original_tex)

    # Replace TECHNICAL SKILLS section
    skills_pattern = re.compile(r'(%-----------TECHNICAL SKILLS-----------.*?)(?=%-----------WORK EXPERIENCE-----------)', re.DOTALL)
    old_skills_match = skills_pattern.search(tex_after_profile)
    old_skills = old_skills_match.group(1) if old_skills_match else ""
    tex_after_skills = skills_pattern.sub(lambda m: new_skills, tex_after_profile)

    # Replace PROJECTS section
    projects_pattern = re.compile(r'(%-----------PROJECTS-----------.*?)(?=%-----------CERTIFICATIONS-----------)', re.DOTALL)
    old_projects_match = projects_pattern.search(tex_after_skills)
    old_projects = old_projects_match.group(1) if old_projects_match else ""
    tailored_tex = projects_pattern.sub(lambda m: new_projects, tex_after_skills)

    # Compute diffs
    profile_diff = "\n".join(difflib.unified_diff(
        old_profile.splitlines(), new_profile.splitlines(),
        fromfile="Original PROFILE", tofile="Tailored PROFILE", lineterm=""
    ))
    skills_diff = "\n".join(difflib.unified_diff(
        old_skills.splitlines(), new_skills.splitlines(),
        fromfile="Original SKILLS", tofile="Tailored SKILLS", lineterm=""
    ))
    projects_diff = "\n".join(difflib.unified_diff(
        old_projects.splitlines(), new_projects.splitlines(),
        fromfile="Original PROJECTS", tofile="Tailored PROJECTS", lineterm=""
    ))
    full_diff = "\n".join(difflib.unified_diff(
        original_tex.splitlines(), tailored_tex.splitlines(),
        fromfile="data/main.tex", tofile=f"tailored_cv_{company_name}.tex", lineterm=""
    ))

    # Basic LaTeX safety validation
    open_braces = tailored_tex.count("{")
    close_braces = tailored_tex.count("}")
    if open_braces != close_braces:
        raise ValueError(f"LaTeX brace mismatch in tailored CV: {open_braces} open vs {close_braces} close.")

    metadata = {
        "company_name": company_name,
        "job_title": analysis.target_title,
        "job_url": job_url or "",
        "archetype": analysis.archetype,
        "match_score": analysis.match_score,
        "matched_skills": analysis.matched_skills,
        "top_priorities": analysis.top_priorities,
        "referral": {
            "has_referral": bool(referral_name),
            "referral_name": referral_name or "",
            "referral_contact": referral_contact or "",
        },
        "jd_length": len(jd_text),
    }

    return TailoredCVResult(
        tailored_tex=tailored_tex,
        original_tex=original_tex,
        analysis=analysis,
        profile_diff=profile_diff,
        skills_diff=skills_diff,
        projects_diff=projects_diff,
        full_diff=full_diff,
        metadata=metadata
    )
