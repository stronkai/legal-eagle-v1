# app.py - COMPLETE WORKING VERSION WITH ENHANCED SEARCH AND FORMATTING
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
            
            # Using Grok model
            data = {
                "model": "grok-2",  # Grok 4
                "messages": [
                    {"role": "system", "content": """You are Legal Eagle, an expert Australian legal research assistant. 
                    You provide comprehensive legal research following the exact format shown in examples.
                    Always include specific section numbers, real case citations, and direct AustLII links.
                    Focus on practical application and real precedents."""},
                    {"role": "user", "content": clean_prompt}
                ],
                "temperature": 0.7,
                "stream": False
            }
            
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                else:
                    return f"Unexpected response format"
            elif response.status_code == 401:
                return "API authentication failed. Please verify your API key."
            elif response.status_code == 429:
                return "Rate limit exceeded. Please try again later."
            else:
                return f"API Error {response.status_code}"
                
        except Exception as e:
            return f"Error: {str(e)}"

# ============= CONFIGURATION =============
class Config:
    """Public configuration (no sensitive data here)"""
    
    AUSTLII_BASE = "http://www.austlii.edu.au"
    AUSTLII_SEARCH = "http://www7.austlii.edu.au/cgi-bin/viewdb/au/cases/"
    
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
    
    # Map jurisdictions to their main criminal/traffic acts
    JURISDICTION_ACTS = {
        "Victoria": {
            "crimes": "Crimes Act 1958 (Vic)",
            "traffic": "Road Safety Act 1986 (Vic)",
            "bail": "Bail Act 1977 (Vic)",
            "sentencing": "Sentencing Act 1991 (Vic)"
        },
        "New South Wales": {
            "crimes": "Crimes Act 1900 (NSW)",
            "traffic": "Road Transport Act 2013 (NSW)",
            "bail": "Bail Act 2013 (NSW)",
            "sentencing": "Crimes (Sentencing Procedure) Act 1999 (NSW)"
        },
        "Queensland": {
            "crimes": "Criminal Code Act 1899 (Qld)",
            "traffic": "Transport Operations (Road Use Management) Act 1995 (Qld)",
            "bail": "Bail Act 1980 (Qld)",
            "sentencing": "Penalties and Sentences Act 1992 (Qld)"
        },
        "South Australia": {
            "crimes": "Criminal Law Consolidation Act 1935 (SA)",
            "traffic": "Road Traffic Act 1961 (SA)",
            "bail": "Bail Act 1985 (SA)",
            "sentencing": "Criminal Law (Sentencing) Act 1988 (SA)"
        },
        "Western Australia": {
            "crimes": "Criminal Code Act Compilation Act 1913 (WA)",
            "traffic": "Road Traffic Act 1974 (WA)",
            "bail": "Bail Act 1982 (WA)",
            "sentencing": "Sentencing Act 1995 (WA)"
        },
        "Tasmania": {
            "crimes": "Criminal Code Act 1924 (Tas)",
            "traffic": "Road Safety (Alcohol and Drugs) Act 1970 (Tas)",
            "bail": "Bail Act 1994 (Tas)",
            "sentencing": "Sentencing Act 1997 (Tas)"
        },
        "Northern Territory": {
            "crimes": "Criminal Code Act 1983 (NT)",
            "traffic": "Traffic Act 1987 (NT)",
            "bail": "Bail Act 1982 (NT)",
            "sentencing": "Sentencing Act 1995 (NT)"
        },
        "ACT": {
            "crimes": "Crimes Act 1900 (ACT)",
            "traffic": "Road Transport (Safety and Traffic Management) Act 1999 (ACT)",
            "bail": "Bail Act 1992 (ACT)",
            "sentencing": "Crimes (Sentencing) Act 2005 (ACT)"
        },
        "Commonwealth": {
            "crimes": "Criminal Code Act 1995 (Cth)",
            "traffic": "N/A",
            "bail": "Crimes Act 1914 (Cth)",
            "sentencing": "Crimes Act 1914 (Cth)"
        }
    }

# ============= AUSTLII INTEGRATION =============
class AustLIISearcher:
    """Enhanced AustLII search integration"""
    
    @staticmethod
    def search_cases(query: str, jurisdiction: str, limit: int = 10) -> List[Dict]:
        """Enhanced search for AustLII cases"""
        try:
            clean_query = SecurityManager.sanitize_input(query)
            jurisdiction_code = Config.JURISDICTION_MAP.get(jurisdiction, "au")
            
            # Multiple search strategies for better results
            search_urls = [
                f"http://www.austlii.edu.au/cgi-bin/sinosrch.cgi?query={clean_query}&results=50&submit=Search&rank=on&callback=on&legisopt=&view=relevance&max=50&meta=%2Fau%2Fcases%2F{jurisdiction_code}%2F",
                f"http://www7.austlii.edu.au/cgi-bin/sinosrch.cgi?method=auto&query={clean_query}+{jurisdiction}&results=20",
                f"http://www.austlii.edu.au/cgi-bin/sinosrch.cgi?query={clean_query.replace(' ', '+')}+{jurisdiction}+2023+OR+2024&results=20"
            ]
            
            all_cases = []
            
            for search_url in search_urls:
                try:
                    response = requests.get(search_url, timeout=5)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Find all links that look like case citations
                        for link in soup.find_all('a', href=True):
                            href = link.get('href', '')
                            text = link.get_text(strip=True)
                            
                            # Check if this looks like a case
                            if '/cases/' in href and (
                                '[' in text or 
                                'v ' in text or 
                                'Police' in text or
                                'R v' in text or
                                'DPP' in text
                            ):
                                # Extract case details
                                case = {
                                    'title': text,
                                    'url': f"http://www.austlii.edu.au{href}" if not href.startswith('http') else href
                                }
                                
                                # Try to extract citation
                                if '[' in text and ']' in text:
                                    citation_start = text.find('[')
                                    citation_end = text.find(']', citation_start) + 1
                                    case['citation'] = text[citation_start:citation_end]
                                else:
                                    case['citation'] = 'Citation pending'
                                
                                # Extract year if possible
                                import re
                                year_match = re.search(r'\b(20\d{2}|19\d{2})\b', text)
                                if year_match:
                                    case['year'] = year_match.group()
                                
                                # Add summary
                                parent = link.parent
                                if parent:
                                    summary_text = parent.get_text()[:500]
                                    case['summary'] = summary_text
                                else:
                                    case['summary'] = f"Case involving {clean_query}"
                                
                                # Avoid duplicates
                                if not any(c.get('title') == case['title'] for c in all_cases):
                                    all_cases.append(case)
                                
                                if len(all_cases) >= limit:
                                    break
                
                except:
                    continue
            
            # If still no real cases, provide structured placeholder
            if not all_cases:
                all_cases = [
                    {
                        'title': f'Search for "{clean_query}" cases in {jurisdiction}',
                        'citation': 'Pending search refinement',
                        'url': f'http://www.austlii.edu.au/cgi-bin/sinosrch.cgi?query={clean_query}',
                        'summary': 'Please refine your search or check AustLII directly for specific cases.',
                        'year': '2024'
                    }
                ]
            
            return all_cases[:limit]
            
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
                        
                        # Search AustLII
                        cases = []
                        try:
                            cases = AustLIISearcher.search_cases(query, jurisdiction)
                            progress_text.text(f"✅ Found {len(cases)} cases")
                        except Exception as e:
                            st.error(f"Search error: {str(e)}")
                        
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
                                        content = file.read().decode('utf-8')
                                        context += content[:5000] + "\n"
                                    elif file.type == "application/pdf":
                                        pdf_reader = PyPDF2.PdfReader(file)
                                        for i, page in enumerate(pdf_reader.pages[:10]):
                                            page_text = page.extract_text()
                                            context += page_text[:1000] + "\n"
                                except Exception as e:
                                    st.warning(f"Error reading {file.name}: {str(e)}")
                        
                        progress_text.text("🤖 Analyzing with Grok AI...")
                        
                        # Get jurisdiction-specific acts
                        acts = Config.JURISDICTION_ACTS.get(jurisdiction, {})
                        
                        # Build enhanced prompt based on the template document
                        prompt = f"""# Legal Eagle: {jurisdiction} Legal Research Summary

Act as Legal Eagle for {jurisdiction} legal research.

**Query Analysis**: {query}
Context from files: {context[:1000] if context else 'No additional context'}

The query involves: {query}

CRITICAL INSTRUCTIONS - Format your response EXACTLY like this example:

## Summarized Legislation
Key provisions from {jurisdiction} statutes relevant to {query}. These often result in compounded charges, leading to disqualification, fines, or imprisonment. 

List the specific sections from these acts:
- {acts.get('crimes', 'Criminal Act')}
- {acts.get('traffic', 'Traffic Act')}  
- {acts.get('sentencing', 'Sentencing Act')}

For EACH relevant section provide:
- **[Act Name], s [Number] ([Section Title])**: [What it prohibits]. Penalties: [Specific penalties]. *Relevance and Parity*: [Why this applies to the query, how it's been applied in similar cases, severity level].

## Recent Cases (Past 2 Years)
Searched AustLII for {jurisdiction} Magistrates/Supreme Court decisions from 2022-2024 involving {query}. Focus on high-parity cases with similar facts.

For EACH case provide in this format:
- **Case Name [Year] Court Citation (Court Name, decided Year)**: [Facts of case - defendant did X with Y result]. Convicted of [specific charges under sections]. Sentence: [exact sentence]. *Relevance and Parity*: [Why this case matches the query, how it's persuasive for defense or prosecution, specific similarities].

Include at least 4 recent cases with full details.

## Common Law Precedents  
Key older precedents (pre-2022) from AustLII searches, establishing principles for {query} in {jurisdiction}. These set sentencing guidelines and are binding/persuasive.

For EACH precedent:
- **Case Name (Year) Citation (Court)**: [Key facts]. Convicted under [sections]; sentence: [outcome]. Precedent: [What principle this established]. *Relevance and Parity*: [How this applies to current query, whether it supports harsher or lenient sentencing].

Include at least 3 established precedents.

## Penalties Table
Create a comparison table:
| Offense | Section | Minimum Penalty | Maximum Penalty | Typical First Offense | Typical Repeat Offense |
|---------|---------|-----------------|-----------------|----------------------|------------------------|
| [offense] | s[num] | [penalty] | [penalty] | [outcome] | [outcome] |

## Strategic Recommendations
Based on the legislation and cases:
1. **Immediate Actions**: [Specific steps with timeframes]
2. **Evidence Required**: [List with importance ratings]  
3. **Mitigation Strategies**: [e.g., early guilty plea for discounts up to 40% under Sentencing Act]
4. **Risk Assessment**: [Likelihood of custodial sentence, disqualification periods]

## Overall Advice
These elements suggest potential for [summarize likely penalties based on precedents]. Recommend [specific strategy]. For court use, cite high-parity cases to argue sentencing bands. 

**Important Note**: Consult a qualified {jurisdiction} lawyer for tailored advice; this is not legal advice.

Cases found in search:
"""
                        # Add case details
                        for i, case in enumerate(cases[:8], 1):
                            prompt += f"\n{i}. {case.get('title', '')}"
                            if case.get('citation'):
                                prompt += f" {case.get('citation')}"
                            if case.get('url'):
                                prompt += f" - Link: {case.get('url')}"
                        
                        prompt += f"""

REMEMBER: 
- Use REAL case names and citations (not "Demo Case" or placeholders)
- Include specific section numbers (e.g., s 77, s 45)
- Provide actual penalties from the legislation
- Focus on {jurisdiction} law specifically
- Match the format of the example EXACTLY"""
                        
                        # Get AI analysis
                        analysis = ""
                        try:
                            if api_configured:
                                progress_text.text("🤖 Generating comprehensive legal analysis...")
                                analysis = APIProxy.call_grok_api(prompt, st.session_state.session_id)
                                progress_text.text("✅ Analysis complete!")
                            else:
                                analysis = "Demo mode - Add Grok API key for full analysis"
                                progress_text.text("⚠️ Running in demo mode")
                        except Exception as e:
                            st.error(f"Analysis error: {str(e)}")
                            analysis = f"Error: {str(e)}"
                        
                        # Store results
                        st.session_state.research_results = {
                            'query': query,
                            'jurisdiction': jurisdiction,
                            'cases': cases,
                            'analysis': analysis,
                            'timestamp': datetime.now()
                        }
                        
                        progress_text.empty()
                        st.success("✅ Research complete! Click the 'Results' tab above ☝️")
                        
                    except Exception as e:
                        st.error(f"Unexpected error: {str(e)}")
    
    with tab2:
        if st.session_state.research_results:
            results = st.session_state.research_results
            
            # Results header
            st.markdown("### 📋 Legal Eagle Research Results")
            
            # Summary box
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Jurisdiction", results['jurisdiction'])
            with col2:
                st.metric("Query", results['query'][:30] + "...")
            with col3:
                st.metric("Generated", results['timestamp'].strftime('%Y-%m-%d %H:%M'))
            
            st.markdown("---")
            
            # AI Analysis
            st.markdown(results['analysis'])
            
            # Export section
            st.markdown("---")
            st.markdown("### 📤 Export Options")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📄 Export to Word", use_container_width=True):
                    st.info("Premium feature - Export to Word")
            with col2:
                if st.button("📑 Export to PDF", use_container_width=True):
                    st.info("Premium feature - Export to PDF")
        else:
            st.info("👈 No results yet. Run a search in the Research tab.")
    
    with tab3:
        st.markdown("""
        ### About Legal Eagle
        
        Legal Eagle is an AI-powered legal research assistant for Australian lawyers.
        
        **Features:**
        - 🔍 Search Australian legal databases (AustLII)
        - 🤖 AI-powered case analysis with Grok
        - 📊 Comprehensive legal research reports
        - 🎯 Jurisdiction-specific results
        
        **Pricing (After Beta):**
        - Starter: $49/month
        - Professional: $99/month
        - Firm: $299/month
        
        Beta users get 50% lifetime discount!
        """)

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Legal Eagle Beta | © 2025 | Not a substitute for professional legal advice</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
