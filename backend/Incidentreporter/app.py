import os
import logging
import requests
from flask import Flask, render_template, request, jsonify
from llm_reporter import IncidentReporter

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Initialize the incident reporter
incident_reporter = IncidentReporter()

@app.route('/')
def index():
    """Render the main page with the incident reporting form."""
    return render_template('index.html')

@app.route('/quick')
def quick_report():
    """Render the CarPlay-compatible quick report page."""
    google_maps_key = os.environ.get('GOOGLE_MAPS_API_KEY', '')
    return render_template('quick_report.html', google_maps_key=google_maps_key)

@app.route('/geocode', methods=['POST'])
def geocode_location():
    """Convert coordinates to human-readable address using Google Maps API."""
    try:
        data = request.get_json()
        lat = data.get('lat')
        lng = data.get('lng')
        
        if not lat or not lng:
            return jsonify({
                'error': 'Latitude and longitude are required',
                'success': False
            }), 400
        
        # Use Google Maps Geocoding API
        google_maps_key = os.environ.get('GOOGLE_MAPS_API_KEY')
        if not google_maps_key:
            return jsonify({
                'error': 'Google Maps API key not configured',
                'success': False
            }), 500
        
        # Reverse geocoding to get address
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'latlng': f"{lat},{lng}",
            'key': google_maps_key,
            'result_type': 'street_address|route|intersection'
        }
        
        response = requests.get(geocode_url, params=params)
        response.raise_for_status()
        
        geocode_data = response.json()
        
        if geocode_data['status'] != 'OK' or not geocode_data['results']:
            return jsonify({
                'error': 'Could not determine location from coordinates',
                'success': False
            }), 400
        
        result = geocode_data['results'][0]
        address = result['formatted_address']
        
        # Extract road information for AI analysis
        road_info = extract_road_info(result)
        
        return jsonify({
            'success': True,
            'address': address,
            'road_info': road_info,
            'coordinates': {'lat': lat, 'lng': lng}
        })
        
    except requests.RequestException as e:
        app.logger.error(f"Google Maps API error: {str(e)}")
        return jsonify({
            'error': 'Failed to get location information',
            'success': False
        }), 500
        
    except Exception as e:
        app.logger.error(f"Geocoding error: {str(e)}")
        return jsonify({
            'error': 'Failed to process location',
            'success': False
        }), 500

@app.route('/smart-report', methods=['POST'])
def smart_report():
    """Create an AI-enhanced incident report with automatic location and lane analysis."""
    try:
        data = request.get_json()
        
        incident_type = data.get('incident_type')
        coordinates = data.get('coordinates', {})
        road_info = data.get('road_info', {})
        
        if not incident_type:
            return jsonify({
                'error': 'Incident type is required',
                'success': False
            }), 400
        
        # Get address from geocode data if available
        address = data.get('address')
        
        # Always use smart fallback for reliability (AI quota issues)
        enhanced_report = create_smart_fallback_report(incident_type, coordinates, road_info, address)
        app.logger.info(f"Created smart report for {incident_type} at {address or 'current location'}")
        
        return jsonify({
            'success': True,
            'incident_report': enhanced_report
        })
        
    except Exception as e:
        app.logger.error(f"Smart report error: {str(e)}")
        return jsonify({
            'error': 'Failed to create smart report',
            'success': False
        }), 500

def extract_road_info(geocode_result):
    """Extract useful road information from Google Maps geocoding result."""
    road_info = {
        'road_type': 'unknown',
        'speed_limit_estimate': None,
        'typical_lanes': None,
        'is_highway': False,
        'is_intersection': False
    }
    
    # Analyze address components
    for component in geocode_result.get('address_components', []):
        types = component.get('types', [])
        name = component.get('long_name', '').lower()
        
        # Detect road type
        if 'route' in types:
            if any(highway in name for highway in ['interstate', 'highway', 'freeway', 'i-']):
                road_info['road_type'] = 'highway'
                road_info['is_highway'] = True
                road_info['typical_lanes'] = 4
                road_info['speed_limit_estimate'] = 70
            elif any(arterial in name for arterial in ['boulevard', 'avenue', 'blvd', 'ave']):
                road_info['road_type'] = 'arterial'
                road_info['typical_lanes'] = 3
                road_info['speed_limit_estimate'] = 45
            else:
                road_info['road_type'] = 'street'
                road_info['typical_lanes'] = 2
                road_info['speed_limit_estimate'] = 35
        
        # Detect intersection
        if 'intersection' in types:
            road_info['is_intersection'] = True
    
    return road_info

def create_smart_fallback_report(incident_type, coordinates, road_info, address=None):
    """Create simple incident report for location reporting."""
    from datetime import datetime
    
    # Use actual address from Google Maps if available
    location = address or "Current location"
    
    # Simple incident report - just the essentials for location reporting
    return {
        'incident_type': incident_type,
        'location': location,
        'description': f"Incident reported: {incident_type} at {location}",
        'reported_at': datetime.utcnow().isoformat() + 'Z',
        'coordinates': coordinates,
        'road_info': road_info,
        'processing_method': 'location_based_reporting',
        'status': 'reported'
    }

@app.route('/report', methods=['POST'])
def report_incident():
    """
    API endpoint to process incident reports.
    Accepts JSON with structured incident data or natural language message.
    Returns structured JSON incident report.
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'No JSON data provided',
                'success': False
            }), 400
        
        # Check if this is structured data (from form dropdowns) or natural language
        if 'incident_type' in data and 'location' in data:
            # Structured data from form
            result = create_structured_report(data)
        else:
            # Natural language processing (fallback to AI if available)
            message = data.get('message', '').strip()
            
            if not message:
                return jsonify({
                    'error': 'Message field is required and cannot be empty',
                    'success': False
                }), 400
            
            # Try AI processing, fallback to basic parsing if API unavailable
            try:
                app.logger.info(f"Processing incident report with AI: {message}")
                result = incident_reporter.generate_report(message)
            except Exception as ai_error:
                app.logger.warning(f"AI processing failed, using basic parsing: {str(ai_error)}")
                result = create_basic_report(message)
        
        return jsonify({
            'success': True,
            'incident_report': result,
            'original_input': data
        })
        
    except ValueError as e:
        app.logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'error': f'Invalid input: {str(e)}',
            'success': False
        }), 400
        
    except Exception as e:
        app.logger.error(f"Error processing incident report: {str(e)}")
        return jsonify({
            'error': 'Failed to process incident report. Please try again.',
            'success': False
        }), 500

def create_structured_report(data):
    """Create a structured report from form data."""
    from datetime import datetime
    
    # Validate required fields
    required_fields = ['incident_type', 'location', 'severity']
    for field in required_fields:
        if not data.get(field):
            raise ValueError(f"Missing required field: {field}")
    
    # Create structured report
    report = {
        'incident_type': data.get('incident_type'),
        'location': data.get('location'),
        'severity': data.get('severity'),
        'description': data.get('description', ''),
        'direction': data.get('direction'),
        'lanes_affected': data.get('lanes_affected'),
        'estimated_delay': data.get('estimated_delay'),
        'time_mentioned': data.get('time_mentioned'),
        'processed_at': datetime.utcnow().isoformat() + 'Z',
        'original_input': data,
        'processing_method': 'structured_form'
    }
    
    # Clean up null/empty values
    for key, value in list(report.items()):
        if value == '' or value is None:
            if key in ['direction', 'lanes_affected', 'estimated_delay', 'time_mentioned']:
                report[key] = None
    
    return report

def create_basic_report(message):
    """Create a basic report from natural language when AI is unavailable."""
    from datetime import datetime
    import re
    
    # Basic keyword detection
    message_lower = message.lower()
    
    # Detect incident type
    incident_type = 'other'
    if any(word in message_lower for word in ['crash', 'accident', 'collision', 'wreck']):
        incident_type = 'accident'
    elif any(word in message_lower for word in ['speed trap', 'police', 'radar', 'cop']):
        incident_type = 'speed_trap'
    elif any(word in message_lower for word in ['construction', 'work zone', 'road work']):
        incident_type = 'construction'
    elif any(word in message_lower for word in ['stalled', 'broken down', 'disabled']):
        incident_type = 'stalled_vehicle'
    elif any(word in message_lower for word in ['debris', 'object in road']):
        incident_type = 'debris'
    elif any(word in message_lower for word in ['closed', 'closure', 'blocked']):
        incident_type = 'road_closure'
    
    # Detect severity
    severity = 'medium'
    if any(word in message_lower for word in ['major', 'severe', 'serious', 'heavy traffic', 'major delays']):
        severity = 'high'
    elif any(word in message_lower for word in ['minor', 'small', 'light', 'cleared']):
        severity = 'low'
    
    # Extract location (basic)
    location = message
    
    # Detect direction
    direction = None
    direction_patterns = ['northbound', 'southbound', 'eastbound', 'westbound', 'north', 'south', 'east', 'west']
    for pattern in direction_patterns:
        if pattern in message_lower:
            direction = pattern
            break
    
    # Detect lanes affected
    lanes_match = re.search(r'(\d+)\s*lane', message_lower)
    lanes_affected = int(lanes_match.group(1)) if lanes_match else None
    
    return {
        'incident_type': incident_type,
        'location': location,
        'severity': severity,
        'description': f"Basic analysis of: {message}",
        'direction': direction,
        'lanes_affected': lanes_affected,
        'estimated_delay': None,
        'time_mentioned': None,
        'processed_at': datetime.utcnow().isoformat() + 'Z',
        'original_input': message,
        'processing_method': 'basic_keyword_detection'
    }

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'traffic-incident-reporter'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
