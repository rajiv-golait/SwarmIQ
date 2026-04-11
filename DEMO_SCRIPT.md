# ~90 second demo script (SwarmIQ)

Use this as a spoken walkthrough while the UI or activity log is visible. Adjust timing to your actual run length.

---

**Hook (10 s)**  
“I’ll ask for something that changes often on the web: *what’s the latest released Claude model?* SwarmIQ turns that into a small research plan, searches and reads pages, extracts claims, negotiates them with votes, then writes a cited report and scores it.”

**Planner (15 s)**  
“Here the planner broke the query into sub-questions and search strings. You can see them in the activity log under `[Plan]`.”

**Parallel research (20 s)**  
“Literature review and summarizer run as parallel branches—two cards or log sections can light up together. They pull DDG results, use Jina Reader where possible, and embed chunks into LanceDB.”

**Gap loop (15 s)**  
“If the first iteration gets thin hits, gap detection flags unanswered questions and we re-plan and re-search. In practice that also spaces out search calls, which helps when the search backend is touchy about bursts.”

**Claims and negotiation (20 s)**  
“The merger combines claims; then negotiation runs in batches. You’ll see lines like `[Negotiate] Round 1 batch 1: N LLM votes for N claims` when voting succeeds. Accepted claims feed synthesis; the rest stay uncertain or rejected.”

**Synthesis and critic (15 s)**  
“The synthesizer writes the markdown report with inline `[n]` citations and a references section. The critic runs a **local** coherence scorer—structure, citations, references, length—not a heavy semantic model—so the score is interpretable. If Groq rate-limits, the log will say so and you may see fallbacks.”

**Close (5 s)**  
“End state: a grounded report when search and negotiation succeed, honest degradation when they don’t, and a score that matches what we actually measure.”

---

**If asked “is it hallucinating?”**  
Point to accepted vs. uncertain counts, URLs in references, and the “no accepted claims” path if negotiation fails.

**If asked “why did iteration 1 return zero pages?”**  
Cite search provider behavior and the gap-loop retry effect (`LIMITATIONS.md` §2).
