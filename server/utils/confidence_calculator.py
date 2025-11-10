"""
Calculate actual confidence scores for parsed medical data.
This validates the extracted data and provides a real confidence metric.
"""

import re
from datetime import datetime
from typing import Dict, Any, Tuple


class ConfidenceCalculator:
    """Calculate confidence scores based on data quality metrics."""
    
    # Expected core fields for a medical report
    EXPECTED_FIELDS = {
        'patient_name': 10,
        'patient_id': 10,
        'encounter_date': 10,
        'diagnosis': 15,
        'medications': 10,
        'lab_results': 10,
        'imaging_findings': 5,
        'vital_signs': 10,
        'clinician_name': 5,
    }
    
    def calculate_confidence(
        self, 
        parsed_data: Dict[str, Any],
        gemini_confidence: int = None
    ) -> Tuple[int, str, Dict[str, Any]]:
        """
        Calculate real confidence score based on data quality.
        
        Args:
            parsed_data: The extracted JSON data
            gemini_confidence: Gemini's self-reported confidence (optional)
            
        Returns:
            Tuple of (confidence_score, confidence_summary, validation_details)
        """
        if not parsed_data:
            return (0, "No data extracted", {"error": "empty_data"})
        
        validation_details = {}
        total_score = 0
        max_score = 100
        
        # 1. Field Completeness Score (40 points)
        completeness_score, completeness_details = self._check_completeness(parsed_data)
        validation_details['completeness'] = completeness_details
        total_score += completeness_score
        
        # 2. Data Format Validation (30 points)
        format_score, format_details = self._check_formats(parsed_data)
        validation_details['format_validation'] = format_details
        total_score += format_score
        
        # 3. Data Consistency (20 points)
        consistency_score, consistency_details = self._check_consistency(parsed_data)
        validation_details['consistency'] = consistency_details
        total_score += consistency_score
        
        # 4. Gemini Self-Assessment Bonus (10 points)
        if gemini_confidence:
            gemini_score = min(10, gemini_confidence / 10)
            total_score += gemini_score
            validation_details['gemini_confidence'] = gemini_confidence
        
        # Generate summary
        confidence_score = min(100, int(total_score))
        summary = self._generate_summary(confidence_score, validation_details)
        
        return (confidence_score, summary, validation_details)
    
    def _check_completeness(self, data: Dict[str, Any]) -> Tuple[int, Dict]:
        """Check if expected fields are present and non-empty."""
        present_fields = []
        missing_fields = []
        empty_fields = []
        
        for field, weight in self.EXPECTED_FIELDS.items():
            if field in data:
                value = data[field]
                if value and str(value).strip():
                    present_fields.append(field)
                else:
                    empty_fields.append(field)
            else:
                missing_fields.append(field)
        
        # Score: percentage of fields present * 40
        present_count = len(present_fields)
        total_expected = len(self.EXPECTED_FIELDS)
        score = (present_count / total_expected) * 40
        
        details = {
            'score': round(score, 2),
            'present': present_fields,
            'missing': missing_fields,
            'empty': empty_fields,
            'completeness_rate': f"{present_count}/{total_expected}"
        }
        
        return (score, details)
    
    def _check_formats(self, data: Dict[str, Any]) -> Tuple[int, Dict]:
        """Validate data formats (dates, IDs, etc.)."""
        validations = []
        issues = []
        score = 30  # Start with full points, deduct for issues
        
        # Check patient_name format
        if 'patient_name' in data and data['patient_name']:
            name = str(data['patient_name'])
            if len(name) >= 2 and re.match(r'^[A-Za-z\s.-]+$', name):
                validations.append('patient_name: valid format')
            else:
                issues.append('patient_name: suspicious format')
                score -= 5
        
        # Check date formats
        date_fields = ['encounter_date', 'date_of_birth', 'admission_date']
        for field in date_fields:
            if field in data and data[field]:
                date_str = str(data[field])
                if self._is_valid_date(date_str):
                    validations.append(f'{field}: valid date format')
                else:
                    issues.append(f'{field}: invalid date format')
                    score -= 3
        
        # Check patient_id format (should be alphanumeric)
        if 'patient_id' in data and data['patient_id']:
            pid = str(data['patient_id'])
            if len(pid) >= 3:
                validations.append('patient_id: valid length')
            else:
                issues.append('patient_id: suspiciously short')
                score -= 5
        
        details = {
            'score': max(0, round(score, 2)),
            'valid_formats': validations,
            'format_issues': issues
        }
        
        return (max(0, score), details)
    
    def _check_consistency(self, data: Dict[str, Any]) -> Tuple[int, Dict]:
        """Check for logical consistency in the data."""
        checks = []
        warnings = []
        score = 20  # Start with full points
        
        # Check if diagnosis exists when medications are prescribed
        if 'medications' in data and data['medications']:
            if 'diagnosis' in data and data['diagnosis']:
                checks.append('diagnosis present with medications')
            else:
                warnings.append('medications without diagnosis')
                score -= 5
        
        # Check if lab_results is structured data
        if 'lab_results' in data and data['lab_results']:
            if isinstance(data['lab_results'], (list, dict)):
                checks.append('lab_results properly structured')
            else:
                warnings.append('lab_results not structured')
                score -= 3
        
        # Check for confidence_score field (Gemini's own assessment)
        if 'confidence_score' in data:
            gemini_conf = data.get('confidence_score', 0)
            if isinstance(gemini_conf, (int, float)) and 0 <= gemini_conf <= 100:
                checks.append(f'gemini confidence: {gemini_conf}')
            else:
                warnings.append('invalid gemini confidence format')
        
        details = {
            'score': max(0, round(score, 2)),
            'consistency_checks': checks,
            'warnings': warnings
        }
        
        return (max(0, score), details)
    
    def _is_valid_date(self, date_str: str) -> bool:
        """Check if string looks like a valid date."""
        # Common date formats
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # 2025-11-03
            r'\d{2}/\d{2}/\d{4}',  # 11/03/2025 or 03/11/2025
            r'\d{2}-\d{2}-\d{4}',  # 03-11-2025
            r'\d{1,2}\s+[A-Za-z]+\s+\d{4}',  # 3 November 2025
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, date_str):
                return True
        return False
    
    def _generate_summary(self, score: int, details: Dict) -> str:
        """Generate human-readable confidence summary."""
        if score >= 90:
            quality = "Excellent"
        elif score >= 80:
            quality = "Very Good"
        elif score >= 70:
            quality = "Good"
        elif score >= 60:
            quality = "Fair"
        else:
            quality = "Poor"
        
        completeness = details.get('completeness', {})
        present = len(completeness.get('present', []))
        missing = len(completeness.get('missing', []))
        
        summary = f"{quality} data quality. {present} key fields extracted"
        if missing > 0:
            summary += f", {missing} missing"
        
        format_issues = details.get('format_validation', {}).get('format_issues', [])
        if format_issues:
            summary += f". {len(format_issues)} format warnings"
        
        return summary


# Singleton instance
_calculator = ConfidenceCalculator()


def calculate_confidence(
    parsed_data: Dict[str, Any],
    gemini_confidence: int = None
) -> Tuple[int, str, Dict[str, Any]]:
    """
    Calculate confidence score for parsed medical data.
    
    Args:
        parsed_data: Extracted JSON data
        gemini_confidence: Gemini's self-reported confidence
        
    Returns:
        (confidence_score, confidence_summary, validation_details)
    """
    return _calculator.calculate_confidence(parsed_data, gemini_confidence)
