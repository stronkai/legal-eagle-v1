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
            
            # FIXED: Correct Grok API endpoint and model name
            data = {
                "model": "grok-beta",  # or "grok-2-latest" or "grok-2-mini"
                "messages": [
                    {"role": "system", "content": "You are an expert Australian legal research assistant specializing in Australian law, cases, and legal procedures."},
                    {"role": "user", "content": clean_prompt}
                ],
                "max_tokens": 4000,
                "temperature": 0.7,
                "stream": False
            }
            
            # FIXED: Correct xAI API endpoint
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",  # Correct endpoint
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                else:
                    return "Unexpected response format from API"
            elif response.status_code == 401:
                return "API authentication failed. Please check your API key."
            elif response.status_code == 429:
                return "Rate limit exceeded. Please try again later."
            else:
                print(f"API Error: {response.status_code} - {response.text}")
                return f"API Error: {response.status_code}. Please check your configuration."
                
        except requests.exceptions.Timeout:
            return "Request timed out. Please try again."
        except requests.exceptions.ConnectionError:
            return "Connection error. Please check your internet connection."
        except Exception as e:
            print(f"Internal error: {str(e)}")
            return f"Error processing request: {str(e)}"
