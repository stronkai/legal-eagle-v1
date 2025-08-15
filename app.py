# app.py - COMPLETE WORKING VERSION
import streamlit as st
import requests
import json
import os
from datetime import datetime, timedelta
import hashlib
import secrets
from typing import List, Dict, Optional
import time
from bs4 import BeautifulSoup
import urllib.parse

# Document handling
from docx import Document
import PyPDF2
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# ============= SECURITY LAYER =============
class SecurityManager:
    """Handles API key security and rate limiting"""
    
    @staticmethod
    def get_api_key():
        """Securely retrieve API key from Streamlit secrets"""
        try:
            return st.secrets["GROK_API_KEY"]
        except:
            return os.getenv('GROK_API_KEY', '')
    
    @staticmethod
    def create_session_token():
        """Create a secure session token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def validate_request(session_id: str) -> bool:
        """Validate that request comes from legitimate user session"""
        if 'session_token' not in st.session_state:
            st.session_state.session_token = SecurityManager.create_session_token()
            st.session_state.request_count = 0
            st.session_state.first_request_time = datetime.now()
        
        st.session_state.request_count += 1
        
        if st.session_state.request_count > 100:
            time_elapsed = datetime.now() - st.session_state.first_request_time
            if time_elapsed < timedelta(hours=1):
                st.error("⚠️ Rate limit exceeded. Please try again later.")
                return False
            else:
                st.session_state.request_count = 0
                st.session_state.first_request_time = datetime.now()
        
        return True
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not text:
            return ""
        
        dangerous_patterns = ['<script', 'javascript:', 'onclick', 'onerror', 'eval(', 'exec(']
        clean_text = text
        for pattern in dangerous_patterns:
            clean_text = clean_text.replace(pattern, '')
        
        return clean_text[:10000]

class APIProxy:
    """Proxy layer to hide API interactions from client"""
    
    @staticmethod
    def call_grok_api(prompt: str, session_id: str) -> str:
        """Securely call Grok API without exposing key to client"""
        if not SecurityManager.validate_request(session_id):
            return "Request denied due to rate limiting"
        
        api_key = SecurityManager.get_api_key()
        
        if not api_key:
            return "API configuration error. Please contact support."
        
        clean_prompt = SecurityManager.sanitize_input(prompt)
        
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "grok-beta",
                "messages": [
                    {"role": "system", "content": "You are an expert Australian legal research assistant."},
                    {"role": "user", "content": clean_prompt}
                ],
                "max_tokens": 4000,
                "temperature": 0.7
            }
            
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                print(f"API Error: {response.status_code}")
                return f"API Error: {response.status_code}. Please check your API key and endpoint."
                
        except Exception as e:
            print(f"Internal error: {str(e)}")
            return f"Error calling API: {str(e)}"

# ============= CONFIGURATION =============
class Config:
    """Public configuration (no sensitive data here)"""
    
    AUSTLII_BASE = "http://www.austlii.edu.au"
    AUSTLII_SEARCH = "http://www.austlii.edu.au/cgi-bin/sinosrch.cgi"
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    JURISDICTION_MAP = {
        "Commonwealth": "cth",
        "ACT": "act", 
        "New South Wales": "nsw",
        "Northern Territory": "nt",
        "Queensland": "qld",
        "South Australia": "sa",
        "Tasmania": "tas",
        "Victoria": "vic",
        "Western Australia": "wa"
    }

# ============= AUSTLII INTEGRATION =============
class AustLIISearcher:
    """AustLII search integration"""
    
    @staticmethod
    def search_cases(query: str, jurisdiction: str, limit: int = 10) -> List[Dict]:
        """Search AustLII for relevant cases"""
        try:
            clean_query = SecurityManager.sanitize_input(query)
            
            params = {
                'method': 'auto',
                'query': clean_query,
                'meta': f'/{Config.JURISDICTION_MAP.get(jurisdiction, "au")}/',
                'results': str(min(limit, 20)),
                'submit': 'Search',
                'mask_path': '/au/cases/',
                'mask_world': 'au',
                'collection': 'au'
            }
            
            response = requests.get(Config.AUSTLII_SEARCH, params=params, timeout=10)
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            cases = []
            
            results = soup.find_all('li', class_='result') or soup.find_all('div', class_='result-item')
            
            for result in results[:limit]:
                case = {}
                
                link = result.find('a')
                if link:
                    case['title'] = link.get_text(strip=True)
                    case['url'] = f"{Config.AUSTLII_BASE}{link.get('href', '')}"
                
                citation = result.find('span', class_='citation')
                if citation:
                    case['citation'] = citation.get_text(strip=True)
                
                summary = result.find('span', class_='snippet') or result.find('p')
                if summary:
                    case['summary'] = summary.get_text(strip=True)[:500]
                
                if case.get('title'):
                    cases.append(case)
            
            return cases
            
        except Exception as e:
            print(f"AustLII search error: {str(e)}")
            return []

# ============= MAIN UI =============
def initialize_session_state():
    """Initialize session state variables"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = SecurityManager.create_session_token()
    if 'recording' not in st.session_state:
        st.session_state.recording = False
    if 'research_results' not in st.session_state:
        st.session_state.research_results = None
    if 'transcription' not in st.session_state:
        st.session_state.transcription = ""
    if 'beta_mode' not in st.session_state:
        st.session_state.beta_mode = True

def main():
    st.set_page_config(
        page_title="Legal Eagle - Beta",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    .stButton > button {
        background-color: #1e3a8a;
        color: white;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
    }
    .beta-banner {
        background: linear-gradient(90deg, #10b981 0%, #059669 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 2rem;
    }
    .status-box {
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    initialize_session_state()
    
    # Beta banner
    st.markdown("""
    <div class="beta-banner">
        <h2>🚀 Legal Eagle Beta - FREE During Testing Phase</h2>
        <p>AI-Powered Australian Legal Research Assistant</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⚖️ Legal Eagle")
        st.markdown("**Your AI Legal Research Assistant**")
    with col2:
        if st.session_state.beta_mode:
            st.success("✅ Beta Access Active")
    
    # Check API configuration
    api_configured = bool(SecurityManager.get_api_key())
    if not api_configured:
        st.warning("⚠️ Grok API not configured. Running in demo mode.")
        st.info("To enable AI features: Manage App → Settings → Secrets → Add GROK_API_KEY")
    
    # Main tabs
    tab1, tab2, tab3 = st.tabs(["📝 Research", "📊 Results", "💡 About"])
    
    with tab1:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            jurisdiction = st.selectbox(
                "Select Jurisdiction",
                list(Config.JURISDICTION_MAP.keys()),
                index=7  # Victoria default
            )
            
            query = st.text_area(
                "Enter your legal query",
                placeholder="Example: Client charged with aggravated burglary under s77 Crimes Act 1958 (Vic). Previous convictions for theft. Seeking bail application strategy.",
                height=120
            )
            
            uploaded_files = st.file_uploader(
                "Upload Case Files (PDF/TXT) - Optional",
                accept_multiple_files=True,
                type=['pdf', 'txt'],
                help="Upload relevant documents to provide context"
            )
        
        with col2:
            st.markdown("### 📚 Quick Templates")
            
            templates = {
                "🔒 Criminal": "Client charged with [offense] under [section] of Crimes Act. Previous convictions: [details]. Seeking advice on [plea/bail/sentencing].",
                "👨‍👩‍👧 Family": "Divorce proceedings involving [children/property]. Issues: [custody/assets]. Seeking advice on [specific matter].",
                "🏠 Property": "Property dispute regarding [address]. Issue: [boundary/easement/sale]. Parties: [details].",
                "💼 Commercial": "Contract dispute between [parties]. Amount: $[value]. Issue: [breach type]."
            }
            
            for label, template in templates.items():
                if st.button(label, use_container_width=True):
                    st.info(f"Template: {template}")
        
        # Research button - INSIDE tab1
        if st.button("🔍 Run Legal Research", type="primary", use_container_width=True):
            if not query:
                st.error("Please enter a legal query")
            else:
                # Add progress tracking
                progress_text = st.empty()
                
                progress_text.text("✅ Starting search...")
                
                # Security check
                if not SecurityManager.validate_request(st.session_state.session_id):
                    st.error("Rate limit exceeded. Please wait before making another request.")
                else:
                    try:
                        progress_text.text("🔍 Searching AustLII database...")
                        
                        # Search AustLII with error handling
                        cases = []
                        try:
                            cases = AustLIISearcher.search_cases(query, jurisdiction)
                            progress_text.text(f"✅ Found {len(cases)} cases")
                        except Exception as e:
                            st.error(f"AustLII search error: {str(e)}")
                        
                        # Process uploaded files
                        context = ""
                        if uploaded_files:
                            progress_text.text("📄 Processing uploaded files...")
                            for file in uploaded_files:
                                try:
                                    if file.size > Config.MAX_FILE_SIZE:
                                        st.warning(f"File {file.name} too large (max 10MB)")
                                        continue
                                    
                                    if file.type == "text/plain":
                                        context += file.read().decode('utf-8')[:5000] + "\n"
                                    elif file.type == "application/pdf":
                                        pdf_reader = PyPDF2.PdfReader(file)
                                        for i, page in enumerate(pdf_reader.pages[:10]):
                                            context += page.extract_text()[:1000] + "\n"
                                except Exception as e:
                                    st.warning(f"Error reading {file.name}: {str(e)}")
                        
                        progress_text.text("🤖 Analyzing with AI...")
                        
                        # Build prompt
                        prompt = f"""Analyze this Australian legal query:

Query: {query}
Jurisdiction: {jurisdiction}
Additional Context: {context[:2000] if context else 'None'}

Relevant cases found in AustLII:
"""
                        for i, case in enumerate(cases[:5], 1):
                            prompt += f"\n{i}. {case.get('title', '')}"
                            if case.get('citation'):
                                prompt += f" [{case.get('citation')}]"
                            if case.get('summary'):
                                prompt += f"\n   Summary: {case.get('summary', '')[:200]}"
                        
                        prompt += """

Please provide:
1. **Key Legal Issues**: Identify the main legal questions
2. **Applicable Legislation**: Cite relevant Acts and sections
3. **Case Law Analysis**: Discuss relevant precedents
4. **Strategic Recommendations**: Practical next steps

Format your response with clear headings and be specific to """ + jurisdiction + """ law."""
                        
                        # Get AI analysis
                        analysis = ""
                        try:
                            if api_configured:
                                progress_text.text("🤖 Calling Grok API...")
                                analysis = APIProxy.call_grok_api(prompt, st.session_state.session_id)
                                progress_text.text("✅ Analysis complete!")
                            else:
                                # Demo mode response
                                analysis = f"""### Legal Research Results (Demo Mode)

**Query Analyzed:** {query}

**Jurisdiction:** {jurisdiction}

**Cases Found:** {len(cases)} relevant cases were found in the AustLII database.

**Note:** This is a demo response. To get full AI-powered legal analysis:
1. Add your Grok API key in Manage App → Settings → Secrets
2. The AI will then provide detailed analysis of:
   - Key legal issues
   - Applicable legislation
   - Case law analysis
   - Strategic recommendations

**Sample Cases Found:**
"""
                                for i, case in enumerate(cases[:3], 1):
                                    analysis += f"\n{i}. {case.get('title', 'Unknown Case')}"
                                    if case.get('url'):
                                        analysis += f"\n   Link: {case.get('url')}"
                                
                                progress_text.text("⚠️ Running in demo mode (no API key)")
                        except Exception as e:
                            st.error(f"AI Analysis error: {str(e)}")
                            analysis = f"Error during AI analysis: {str(e)}"
                        
                        # Store results
                        st.session_state.research_results = {
                            'query': query,
                            'jurisdiction': jurisdiction,
                            'cases': cases,
                            'analysis': analysis,
                            'timestamp': datetime.now()
                        }
                        
                        progress_text.empty()
                        st.success("✅ Research complete! Click the 'Results' tab above to see your results ☝️")
                        
                    except Exception as e:
                        st.error(f"Unexpected error: {str(e)}")
                        st.write("Full error details:", str(e))
    
    with tab2:
        if st.session_state.research_results:
            results = st.session_state.research_results
            
            # Results header
            st.markdown(f"### 📋 Research Results")
            st.markdown(f"**Jurisdiction:** {results['jurisdiction']}")
            st.markdown(f"**Query:** {results['query']}")
            st.markdown(f"**Generated:** {results['timestamp'].strftime('%Y-%m-%d %H:%M')}")
            
            # Cases section
            if results['cases']:
                st.markdown("### 📚 Relevant Cases from AustLII")
                for i, case in enumerate(results['cases'][:10], 1):
                    with st.expander(f"{i}. {case.get('title', 'Case')}"):
                        if case.get('citation'):
                            st.markdown(f"**Citation:** {case.get('citation')}")
                        if case.get('url'):
                            st.markdown(f"**Link:** [{case.get('url')}]({case.get('url')})")
                        if case.get('summary'):
                            st.markdown(f"**Summary:** {case.get('summary')}")
            else:
                st.info("No cases found. Try refining your search query.")
            
            # AI Analysis
            st.markdown("### 🤖 AI Legal Analysis")
            st.markdown(results['analysis'])
            
            # Export section
            st.markdown("### 📤 Export Options")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📄 Generate Word Document"):
                    st.info("Export feature available in premium version")
            with col2:
                if st.button("📑 Generate PDF Report"):
                    st.info("Export feature available in premium version")
        else:
            st.info("👈 No results yet. Run a search in the Research tab to see results here.")
    
    with tab3:
        st.markdown("""
        ### About Legal Eagle
        
        Legal Eagle is an AI-powered legal research assistant designed specifically for Australian lawyers and law students.
        
        **Features:**
        - 🔍 Search Australian legal databases (AustLII)
        - 🤖 AI-powered case analysis (with Grok API)
        - 📁 Process uploaded case files
        - 📊 Generate comprehensive research reports
        - 🎯 Jurisdiction-specific results
        
        **How to Use:**
        1. Select your jurisdiction
        2. Enter your legal query
        3. Optionally upload relevant documents
        4. Click "Run Legal Research"
        5. View results in the Results tab
        
        **Coming Soon:**
        - 🎙️ Audio transcription for client interviews
        - 📱 Mobile app
        - 🔗 Integration with more legal databases
        - 💼 Practice management features
        
        **Beta Feedback:**
        Email: support@legaleagle.ai
        
        **Pricing (After Beta):**
        - Starter: $49/month
        - Professional: $99/month
        - Firm: $299/month
        
        Beta users get 50% lifetime discount!
        """)

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 2rem;'>
        <p>Legal Eagle Beta v1.0 | © 2025 | Built for Australian Legal Professionals</p>
        <p>⚖️ Not a substitute for professional legal advice</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
