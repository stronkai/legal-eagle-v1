# app.py - SECURE VERSION FOR DEPLOYMENT
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
from functools import wraps
import hmac

# Document handling
from docx import Document
import PyPDF2
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Audio handling
#import sounddevice as sd
#import soundfile as sf
import numpy as np
import tempfile
#import speech_recognition as sr

# ============= SECURITY LAYER =============
class SecurityManager:
    """Handles API key security and rate limiting"""
    
    @staticmethod
    def get_api_key():
        """Securely retrieve API key from Streamlit secrets"""
        try:
            # For Streamlit Cloud deployment
            return st.secrets["GROK_API_KEY"]
        except:
            # For local development only
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
        
        # Rate limiting - max 100 requests per hour per session
        st.session_state.request_count += 1
        
        if st.session_state.request_count > 100:
            time_elapsed = datetime.now() - st.session_state.first_request_time
            if time_elapsed < timedelta(hours=1):
                st.error("⚠️ Rate limit exceeded. Please try again later.")
                return False
            else:
                # Reset counter after an hour
                st.session_state.request_count = 0
                st.session_state.first_request_time = datetime.now()
        
        return True
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not text:
            return ""
        
        # Remove potential harmful patterns
        dangerous_patterns = ['<script', 'javascript:', 'onclick', 'onerror', 'eval(', 'exec(']
        clean_text = text
        for pattern in dangerous_patterns:
            clean_text = clean_text.replace(pattern, '')
        
        # Limit length to prevent DOS
        return clean_text[:10000]

class APIProxy:
    """Proxy layer to hide API interactions from client"""
    
    @staticmethod
    def call_grok_api(prompt: str, session_id: str) -> str:
        """
        Securely call Grok API without exposing key to client
        API key NEVER leaves the server
        """
        # Validate session
        if not SecurityManager.validate_request(session_id):
            return "Request denied due to rate limiting"
        
        # Get API key securely (never sent to client)
        api_key = SecurityManager.get_api_key()
        
        if not api_key:
            return "API configuration error. Please contact support."
        
        # Sanitize prompt
        clean_prompt = SecurityManager.sanitize_input(prompt)
        
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "grok-beta",  # Update with actual model
                "messages": [
                    {"role": "system", "content": "You are an expert Australian legal research assistant."},
                    {"role": "user", "content": clean_prompt}
                ],
                "max_tokens": 4000,
                "temperature": 0.7
            }
            
            # Server-side API call - key never exposed to client
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                # Log error server-side, return generic message to client
                print(f"API Error: {response.status_code}")
                return "Service temporarily unavailable. Please try again."
                
        except Exception as e:
            # Log error server-side, never expose internal errors to client
            print(f"Internal error: {str(e)}")
            return "An error occurred processing your request."

# ============= CONFIGURATION =============
class Config:
    """Public configuration (no sensitive data here)"""
    
    # AustLII endpoints (public)
    AUSTLII_BASE = "http://www.austlii.edu.au"
    AUSTLII_SEARCH = "http://www.austlii.edu.au/cgi-bin/sinosrch.cgi"
    
    # Audio settings
    SAMPLE_RATE = 44100
    CHANNELS = 1
    
    # File limits
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Jurisdiction mappings
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
    
    # Future: Crypto payment address (public)
    CRYPTO_WALLET = {
        "ETH": "0x...",  # Add your Ethereum address here
        "BTC": "bc1...",  # Add your Bitcoin address here
        "USDC": "0x..."   # Add your USDC address here
    }

# ============= AUSTLII INTEGRATION =============
class AustLIISearcher:
    """AustLII search integration"""
    
    @staticmethod
    def search_cases(query: str, jurisdiction: str, limit: int = 10) -> List[Dict]:
        """Search AustLII for relevant cases"""
        try:
            # Sanitize query
            clean_query = SecurityManager.sanitize_input(query)
            
            params = {
                'method': 'auto',
                'query': clean_query,
                'meta': f'/{Config.JURISDICTION_MAP.get(jurisdiction, "au")}/',
                'results': str(min(limit, 20)),  # Cap at 20 for performance
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
            
            # Parse results
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

# ============= AUDIO HANDLER =============
class AudioRecorder:
    """Audio recording handler"""
    
    def __init__(self):
        self.recording = False
        self.audio_data = []
        self.sample_rate = Config.SAMPLE_RATE
    
    def start_recording(self):
        """Start recording audio"""
        self.recording = True
        self.audio_data = []
        
        def callback(indata, frames, time, status):
            if self.recording:
                self.audio_data.append(indata.copy())
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=Config.CHANNELS,
            callback=callback
        )
        self.stream.start()
        return True
    
    def stop_recording(self):
        """Stop recording and return audio file path"""
        if not self.recording:
            return None
        
        self.recording = False
        self.stream.stop()
        self.stream.close()
        
        if not self.audio_data:
            return None
        
        audio_array = np.concatenate(self.audio_data, axis=0)
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        sf.write(temp_file.name, audio_array, self.sample_rate)
        
        return temp_file.name
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio file to text"""
        try:
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                audio = recognizer.record(source)
                text = recognizer.recognize_google(audio, language='en-AU')
                return text
        except Exception as e:
            return f"Transcription error: {str(e)}"

# ============= MAIN UI =============
def initialize_session_state():
    """Initialize session state variables"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = SecurityManager.create_session_token()
    if 'audio_recorder' not in st.session_state:
        st.session_state.audio_recorder = AudioRecorder()
    if 'recording' not in st.session_state:
        st.session_state.recording = False
    if 'research_results' not in st.session_state:
        st.session_state.research_results = None
    if 'transcription' not in st.session_state:
        st.session_state.transcription = ""
    if 'beta_mode' not in st.session_state:
        st.session_state.beta_mode = True  # Free during beta

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
        <p>Help us improve! Report bugs to get lifetime discount when we launch.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⚖️ Legal Eagle")
        st.markdown("**AI-Powered Australian Legal Research Assistant**")
    with col2:
        if st.session_state.beta_mode:
            st.success("✅ Beta Access Active")
        else:
            st.info("💎 Premium Version")
    
    # Check API configuration
    if not SecurityManager.get_api_key():
        st.error("⚠️ Service configuration in progress. Please try again later.")
        st.info("Contact support@legaleagle.ai for immediate assistance.")
        return
    
    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Research", "🎙️ Audio", "📊 Results", "💰 Pricing"])
    
    with tab1:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            jurisdiction = st.selectbox(
                "Select Jurisdiction",
                list(Config.JURISDICTION_MAP.keys()),
                index=7  # Victoria default
            )
            
            query = st.text_area(
                "Legal Query",
                placeholder="Example: Client charged with aggravated burglary...",
                height=100
            )
            
            uploaded_files = st.file_uploader(
                "Upload Case Files (PDF/TXT)",
                accept_multiple_files=True,
                type=['pdf', 'txt']
            )
        
        with col2:
            st.markdown("### Quick Templates")
            if st.button("Criminal Law"):
                st.session_state.template = "Client charged with [offense]..."
            if st.button("Family Law"):
                st.session_state.template = "Divorce proceedings with..."
            if st.button("Property Law"):
                st.session_state.template = "Contract dispute regarding..."
    
    with tab2:
        st.markdown("### 🎙️ Record Client Interview")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col2:
            if not st.session_state.recording:
                if st.button("🔴 Start Recording", use_container_width=True):
                    if st.session_state.audio_recorder.start_recording():
                        st.session_state.recording = True
                        st.rerun()
            else:
                st.markdown("**🔴 Recording...**")
                if st.button("⏹️ Stop", use_container_width=True):
                    audio_path = st.session_state.audio_recorder.stop_recording()
                    if audio_path:
                        with st.spinner("Transcribing..."):
                            transcription = st.session_state.audio_recorder.transcribe_audio(audio_path)
                            st.session_state.transcription = transcription
                            st.session_state.recording = False
                            try:
                                os.unlink(audio_path)
                            except:
                                pass
                    st.rerun()
        
        if st.session_state.transcription:
            st.success("✅ Transcribed!")
            st.text_area("Transcription", st.session_state.transcription, height=200)
    
    with tab4:
        st.markdown("### 💰 Pricing - Coming Soon!")
        st.markdown("""
        **Beta Period**: FREE for all users
        
        **After Beta (Q1 2025)**:
        - Starter: $49/month (10 searches/day)
        - Professional: $99/month (50 searches/day)  
        - Firm: $299/month (Unlimited searches)
        
        **Payment Methods** (Coming Soon):
        - Credit/Debit Card via Stripe
        - Cryptocurrency (ETH, BTC, USDC)
        
        **Beta Testers Get**:
        - 50% lifetime discount
        - Priority support
        - Input on new features
        """)
        
        st.info("🎁 Join our beta to lock in your lifetime discount!")
    
    # Research button
    if st.button("🔍 Run Legal Research", type="primary", use_container_width=True):
        if not query:
            st.error("Please enter a legal query")
            return
        
        # Security check
        if not SecurityManager.validate_request(st.session_state.session_id):
            st.error("Rate limit exceeded. Please wait before making another request.")
            return
        
        with st.spinner("Searching AustLII database..."):
            # Search AustLII
            cases = AustLIISearcher.search_cases(query, jurisdiction)
            legislation = []  # Simplified for now
            
            # Process uploaded files
            context = ""
            if uploaded_files:
                for file in uploaded_files:
                    try:
                        if file.size > Config.MAX_FILE_SIZE:
                            st.warning(f"File {file.name} too large (max 10MB)")
                            continue
                        
                        if file.type == "text/plain":
                            context += file.read().decode('utf-8')[:5000] + "\n"
                        elif file.type == "application/pdf":
                            pdf_reader = PyPDF2.PdfReader(file)
                            for i, page in enumerate(pdf_reader.pages[:10]):  # Limit pages
                                context += page.extract_text()[:1000] + "\n"
                    except Exception as e:
                        st.warning(f"Error reading {file.name}")
            
            # Add transcription
            if st.session_state.transcription:
                context += f"\n\nInterview: {st.session_state.transcription[:2000]}"
        
        with st.spinner("Analyzing with AI..."):
            # Build prompt
            prompt = f"""Analyze this Australian legal query:

Query: {query}
Jurisdiction: {jurisdiction}
Context: {context[:2000]}

Cases found:
"""
            for i, case in enumerate(cases[:5], 1):
                prompt += f"{i}. {case.get('title', '')}\n"
            
            prompt += "\nProvide: 1) Legal issues 2) Applicable law 3) Case analysis 4) Strategy"
            
            # Secure API call through proxy
            analysis = APIProxy.call_grok_api(prompt, st.session_state.session_id)
            
            st.session_state.research_results = {
                'query': query,
                'jurisdiction': jurisdiction,
                'cases': cases,
                'analysis': analysis,
                'timestamp': datetime.now()
            }
    
    with tab3:
        if st.session_state.research_results:
            results = st.session_state.research_results
            
            st.markdown(f"### Results for {results['jurisdiction']}")
            st.markdown(f"**Query:** {results['query']}")
            
            if results['cases']:
                st.markdown("### 📚 Relevant Cases")
                for i, case in enumerate(results['cases'][:5], 1):
                    with st.expander(f"{i}. {case.get('title', 'Case')}"):
                        st.markdown(f"**URL:** {case.get('url', 'N/A')}")
                        st.markdown(f"**Summary:** {case.get('summary', 'N/A')}")
            
            st.markdown("### 🤖 AI Analysis")
            st.markdown(results['analysis'])
            
            # Export buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📄 Export Word"):
                    st.info("Export feature available in Premium version")
            with col2:
                if st.button("📑 Export PDF"):
                    st.info("Export feature available in Premium version")
        else:
            st.info("No results yet. Run a search above.")

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>Legal Eagle Beta v1.0 | © 2025 | Built with ❤️ for Australian Lawyers</p>
        <p>Questions? Email: support@legaleagle.ai</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()