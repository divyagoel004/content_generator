import requests
import streamlit as st
import json
from autogen import AssistantAgent, config_list_from_json

# === SerpAPI Tool ===
SERP_API_KEY = "9cf5845377fba47da76c3624cdd2e598a111485c214b4300ba6fb873cbb5d449"

# === MCP Diagram Tool ===
MCP_DIAGRAM_API = "http://20.81.137.128:8000/mcp"

def serp_search(query: str) -> str:
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "engine": "google",
        "num": 5
    }
    response = requests.get(url, params=params).json()
    if "organic_results" in response:
        output = "\n".join([f"- {item['title']}: {item['link']}\n{item.get('snippet', '')}" for item in response["organic_results"]])
        return output
    return "No results found."

def generate_diagram_from_text(description: str) -> str:
    payload = {
        "code": description,
        "theme": "default",
        "background": "white"
    }
    try:
        response = requests.post(MCP_DIAGRAM_API, json=payload)
        print("MCP status:", response.status_code)
        print("MCP response:", response.text)
        if response.status_code == 200:
            result = response.json()
            return result.get("image_url") or result.get("base64_image", "")
    except Exception as e:
        print(f"Diagram generation error: {e}")
    return ""

# === Load LLM config ===
config_list = config_list_from_json(env_or_file="config.txt")
llm_config = {
    "seed": 44,
    "config_list": config_list,
    "temperature": 0
}

# === Agents ===
content_generation_agent = AssistantAgent(
    name="Content_Generation_Agent",
    system_message='''You are a professional slide content generation assistant.
Your job is to generate accurate, structured, engaging presentation content in JSON format. 
Each slide must follow this format:
{
  "Slide 1": {
    "Title": "string",
    "Definition": "Short and precise definition of the concept.",
    "Explanation": "Detailed explanation with facts or insights.",
    "Example": "Real-world or illustrative example.",
    "Bullet_points": "Include Bullet points about the concept in 1-2 lines each and about 4-5 bullet points .",
    "Code": "Optional relevant code block or don't include code if not applicable."
  },
  ...
  "References": ["https://source1", "https://source2"]
}
Guidelines:
- Always include 5 to 10 slides.
- Use search context to ensure authenticity.
- References must be real and used in content.
- Do not hallucinate code.
- Make the tone formal and descriptive as if used for professional client presentation.
''',
    llm_config=llm_config,
    code_execution_config=False,
    human_input_mode="NEVER",
)

critic_agent = AssistantAgent(
    name="Critic_Agent",
    system_message='''You are a senior content reviewer.
Carefully evaluate the JSON presentation content based on:
- factual accuracy
- logical structure
- clarity and depth
- presence of proper references (must be real and relevant URLs)
If the content is excellent, respond only with: APPROVED
Otherwise, list clear, actionable feedback.''',
    llm_config=llm_config,
    code_execution_config=False,
    human_input_mode="NEVER",
)

editor_agent = AssistantAgent(
    name="Editor_Agent",
    system_message='''You are a content editor improving clarity and readability.
Ensure grammar, tone, and bullet points are clean.
look at the content, analyze readability, improve readability - improve ARI Grade Level
Make the language formal and professional for corporate client presentations.
look at the content, analyze readability, improve readability - improve ARI Grade LevelDo not change the structure or remove required fields.
Keep references intact.
And in output you only return the JSON content without any additional text. and ARI Grade Level''',
    llm_config=llm_config,
    code_execution_config=False,
    human_input_mode="NEVER",
)

# === Streamlit UI ===
st.markdown("<h1 style='color:#2F4F4F;'> Content Creator</h1>", unsafe_allow_html=True)
topic = st.text_input("Enter Topic", value=" ")
format_style = st.selectbox("Select Format", ["ppt", "report"])
run_button = st.button("Generate Content")

if run_button and topic:
    st.info("📡 Fetching factual data and generating content. Please wait...")

    def format_task_streamlit(topic, format_style):
        st.markdown("<h4 style='color:#1E90FF;'>🔍 Searching up-to-date context from Google...</h4>", unsafe_allow_html=True)
        search_results = serp_search(topic)

        if format_style == "ppt":
            task = f'''
Generate JSON content for a PowerPoint-style presentation on the topic: "{topic}".
Each slide must follow this structure:
{{
  "Slide 1": {{
    "Title": "...",
    "Definition": "...",
    "Explanation": "...",
    "Example": "...",
    "Bullet_points": "...",
    
  }},
  ...,
  "References": ["https://source1", "https://source2"]
}}
Use this search context:
{search_results}
'''
        elif format_style == "report":
            task = f'''
Write a JSON report on "{topic}" with the format:
{{
  "title": str,
  "summary": str,
  "sections": [{{"heading": str, "content": str}}],
  "references": ["http://source1", ...]
}}
Use this search context:
{search_results}
'''
        else:
            task = f"Write structured content on: {topic}\n\nContext:\n{search_results}"

        MAX_ITERATIONS = 10
        message = task
        loop_count = 0

        for i in range(MAX_ITERATIONS):
            st.markdown(f"<span style='color:#696969;'>🌀 Iteration {i+1} in progress...</span>", unsafe_allow_html=True)
            loop_count += 1
            response_gen = content_generation_agent.generate_reply(messages=[{"role": "user", "content": message}])
            gen_content = response_gen

            response_critic = critic_agent.generate_reply(messages=[{"role": "user", "content": gen_content}])
            critic_feedback = response_critic

            if "APPROVED" in critic_feedback.upper() and loop_count >= 2:
                st.success("✅ Content Approved by Critic Agent after sufficient review.")
                break
            else:
                st.warning("🔁 Refining content with critic feedback...")
                message = f"Revise the following content using the critic feedback:\nContent: {gen_content}\n\nFeedback: {critic_feedback}"
        else:
            st.error("❌ Maximum iterations reached without approval.")
            return

        response_editor = editor_agent.generate_reply(messages=[{"role": "user", "content": gen_content}])
        edited_content = response_editor
        if format_style == "ppt":
                try:
                    json_content = json.loads(edited_content)
                    for slide_key, slide_data in json_content.items():
                        if slide_key.startswith("Slide") and isinstance(slide_data, dict):
                            diagram_code = f"graph TD; A[{slide_data['Title']}] --> B[{slide_data['Explanation'][:30]}...]"
                            diagram_url = generate_diagram_from_text(diagram_code)
                            if diagram_url:
                                slide_data["Diagram"] = f"![Diagram]({diagram_url})"
                except Exception:
                    json_content = {"Raw Text Output": edited_content}
        else:
                try:
                    json_content = json.loads(edited_content)
                except Exception:
                    json_content = {"Raw Text Output": edited_content}

        # try:
        #     # json_content = json.loads(edited_content)
        #     # Add diagram to every slide based on the explanation
        #     for slide_key, slide_data in json_content.items():
        #         if slide_key.startswith("Slide") and isinstance(slide_data, dict):
        #             diagram_code = f"graph TD; A[{slide_data['Title']}] --> B[{slide_data['Explanation'][:30]}...]"
        #             diagram_url = generate_diagram_from_text(diagram_code)
        #             if diagram_url:
        #                 slide_data["Diagram"] = f"![Diagram]({diagram_url})"
        # except Exception:
        #     json_content = {"Raw Text Output": edited_content}

        st.markdown("<h3 style='color:#2E8B57;'>📄 Final Output (Presentation JSON)</h3>", unsafe_allow_html=True)
        st.json(json_content)

    format_task_streamlit(topic, format_style)
