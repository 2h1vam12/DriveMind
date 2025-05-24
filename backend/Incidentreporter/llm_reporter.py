import json
import os
import logging
from openai import OpenAI

class IncidentReporter:
    """
    AI-powered incident reporter that converts natural language descriptions
    into structured JSON incident reports using OpenAI GPT-4.
    """
    
    def __init__(self):
        """Initialize the OpenAI client."""
        self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.logger = logging.getLogger(__name__)
        
    def generate_report(self, user_input: str) -> dict:
        """
        Convert natural language incident description into structured JSON report.
        
        Args:
            user_input (str): Natural language description of the traffic incident
            
        Returns:
            dict: Structured incident report with type, location, severity, etc.
            
        Raises:
            ValueError: If input is invalid
            Exception: If OpenAI API call fails
        """
        if not user_input or not user_input.strip():
            raise ValueError("Input message cannot be empty")
        
        # Create the prompt for incident classification
        system_prompt = """
        You are an expert traffic incident classifier. Your task is to analyze natural language descriptions of traffic incidents and convert them into structured JSON reports.

        For each incident description, extract and classify the following information:
        - incident_type: One of ["accident", "speed_trap", "road_closure", "construction", "weather_hazard", "debris", "stalled_vehicle", "other"]
        - location: The location mentioned in the description (street names, intersections, landmarks, etc.)
        - severity: One of ["low", "medium", "high"] based on the description
        - description: A clean, concise summary of the incident
        - time_mentioned: If a time is mentioned, extract it; otherwise null
        - direction: If direction of travel is mentioned (northbound, eastbound, etc.)
        - lanes_affected: If mentioned, how many lanes are affected
        - estimated_delay: If mentioned or can be inferred, estimated delay in minutes

        Respond with valid JSON in this exact format:
        {
            "incident_type": "string",
            "location": "string", 
            "severity": "string",
            "description": "string",
            "time_mentioned": "string or null",
            "direction": "string or null",
            "lanes_affected": "number or null",
            "estimated_delay": "number or null"
        }
        """
        
        user_prompt = f"Classify this traffic incident: '{user_input}'"
        
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=500
            )
            
            # Parse the JSON response
            result_text = response.choices[0].message.content
            self.logger.debug(f"OpenAI response: {result_text}")
            
            # Parse and validate the JSON
            if not result_text:
                raise ValueError("Empty response from OpenAI")
            incident_report = json.loads(result_text)
            
            # Validate required fields
            required_fields = ['incident_type', 'location', 'severity', 'description']
            for field in required_fields:
                if field not in incident_report:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate incident_type
            valid_types = ["accident", "speed_trap", "road_closure", "construction", 
                          "weather_hazard", "debris", "stalled_vehicle", "other"]
            if incident_report['incident_type'] not in valid_types:
                incident_report['incident_type'] = "other"
            
            # Validate severity
            valid_severities = ["low", "medium", "high"]
            if incident_report['severity'] not in valid_severities:
                incident_report['severity'] = "medium"
            
            # Add metadata
            incident_report['processed_at'] = self._get_current_timestamp()
            incident_report['original_input'] = user_input
            
            return incident_report
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            raise Exception("Failed to parse incident classification response")
            
        except Exception as e:
            self.logger.error(f"OpenAI API error: {e}")
            raise Exception("Failed to classify incident with AI service")
    
    def generate_enhanced_report(self, incident_type: str, coordinates: dict, road_info: dict) -> dict:
        """
        Generate an AI-enhanced incident report using location and road data.
        
        Args:
            incident_type (str): Type of incident
            coordinates (dict): GPS coordinates {'lat': float, 'lng': float}
            road_info (dict): Road information from Google Maps
            
        Returns:
            dict: Enhanced incident report with AI analysis
        """
        if not incident_type:
            raise ValueError("Incident type is required")
        
        # Create enhanced prompt with location context
        system_prompt = """
        You are an expert traffic incident analyst with access to real-time location and road data. 
        Your task is to create a detailed incident report using the provided incident type, GPS coordinates, and road information.

        Analyze the road type, typical traffic patterns, and incident severity to provide:
        - Accurate severity assessment based on road type and incident
        - Intelligent lane impact estimation based on road characteristics
        - Realistic delay estimates considering road capacity
        - Direction analysis if relevant
        - Enhanced description with road context

        Respond with valid JSON in this exact format:
        {
            "incident_type": "string",
            "location": "string", 
            "severity": "string (low/medium/high)",
            "description": "string",
            "time_mentioned": "string or null",
            "direction": "string or null",
            "lanes_affected": "number or null",
            "estimated_delay": "number or null"
        }
        """
        
        # Build context-rich user prompt
        road_context = f"""
        Road Type: {road_info.get('road_type', 'unknown')}
        Highway: {road_info.get('is_highway', False)}
        Typical Lanes: {road_info.get('typical_lanes', 'unknown')}
        Speed Limit Estimate: {road_info.get('speed_limit_estimate', 'unknown')} mph
        Intersection: {road_info.get('is_intersection', False)}
        GPS Coordinates: {coordinates.get('lat', 0):.4f}, {coordinates.get('lng', 0):.4f}
        """
        
        user_prompt = f"""
        Analyze this traffic incident with location context:
        
        Incident Type: {incident_type}
        Location Context: {road_context}
        
        Provide a comprehensive analysis considering:
        - How this incident type typically affects this road type
        - Appropriate severity given the road characteristics
        - Realistic lane impact and delay estimates
        - Current time: just now
        """
        
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500
            )
            
            # Parse the JSON response
            result_text = response.choices[0].message.content
            self.logger.debug(f"OpenAI enhanced response: {result_text}")
            
            # Parse and validate the JSON
            if not result_text:
                raise ValueError("Empty response from OpenAI")
            incident_report = json.loads(result_text)
            
            # Validate required fields
            required_fields = ['incident_type', 'location', 'severity', 'description']
            for field in required_fields:
                if field not in incident_report:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate incident_type
            valid_types = ["accident", "speed_trap", "road_closure", "construction", 
                          "weather_hazard", "debris", "stalled_vehicle", "other"]
            if incident_report['incident_type'] not in valid_types:
                incident_report['incident_type'] = incident_type
            
            # Validate severity
            valid_severities = ["low", "medium", "high"]
            if incident_report['severity'] not in valid_severities:
                incident_report['severity'] = "medium"
            
            # Add metadata
            incident_report['processed_at'] = self._get_current_timestamp()
            incident_report['coordinates'] = coordinates
            incident_report['road_info'] = road_info
            incident_report['processing_method'] = 'ai_enhanced_location_analysis'
            
            return incident_report
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse enhanced JSON response: {e}")
            raise Exception("Failed to parse enhanced incident analysis")
            
        except Exception as e:
            self.logger.error(f"OpenAI enhanced API error: {e}")
            raise Exception("Failed to generate enhanced incident analysis")

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'
