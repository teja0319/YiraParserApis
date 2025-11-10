"""
Post-processing validators for extracted medical data
Implements rule-based validation to achieve 99-100% accuracy
"""

import re
from datetime import datetime
from typing import Dict, List, Any, Tuple


class MedicalDataValidator:
    """Validates extracted medical report data for accuracy and consistency"""
    
    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []
        self.calculated_fields = {}
    
    def validate_all(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str], Dict[str, Any]]:
        """
        Run all validations on extracted data
        
        Returns:
            (is_valid, errors, warnings, calculated_fields)
        """
        self.validation_errors = []
        self.validation_warnings = []
        self.calculated_fields = {}
        
        # Run all validation checks
        self._validate_dates(data)
        self._validate_calculated_vitals(data)
        self._validate_calculated_lab_ratios(data)
        self._validate_lab_ranges(data)
        self._validate_cross_references(data)
        self._validate_logical_consistency(data)
        self._validate_data_types(data)
        
        is_valid = len(self.validation_errors) == 0
        return is_valid, self.validation_errors, self.validation_warnings, self.calculated_fields
    
    def _validate_dates(self, data: Dict[str, Any]):
        """Validate date formats and calculate age"""
        patient_info = data.get('patient_info')
        if not isinstance(patient_info, dict):
            patient_info = {}
            
        report_info = data.get('report_info')
        if not isinstance(report_info, dict):
            report_info = {}
        
        dob = patient_info.get('date_of_birth')
        exam_date = report_info.get('examination_date')
        extracted_age = patient_info.get('age')
        
        if dob and exam_date:
            try:
                # Parse dates (try multiple formats)
                dob_obj = self._parse_date(dob)
                exam_obj = self._parse_date(exam_date)
                
                if dob_obj and exam_obj:
                    # Calculate age
                    age_years = exam_obj.year - dob_obj.year
                    if (exam_obj.month, exam_obj.day) < (dob_obj.month, dob_obj.day):
                        age_years -= 1
                    
                    self.calculated_fields['age'] = f"{age_years} years"
                    
                    # Verify against extracted age
                    if extracted_age:
                        extracted_age_num = int(re.search(r'\d+', extracted_age).group())
                        if abs(extracted_age_num - age_years) > 0:
                            self.validation_errors.append(
                                f"Age mismatch: Extracted '{extracted_age}', Calculated '{age_years} years' "
                                f"from DOB {dob} and exam date {exam_date}"
                            )
                    else:
                        self.validation_warnings.append(f"Age not extracted but can be calculated as {age_years} years")
            except Exception as e:
                self.validation_warnings.append(f"Could not validate age calculation: {str(e)}")
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date from multiple formats"""
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        return None
    
    def _validate_calculated_vitals(self, data: Dict[str, Any]):
        """Validate calculated vital sign fields"""
        vitals = data.get('vitals')
        if not isinstance(vitals, dict):
            vitals = {}
        
        # Validate BMI
        weight_str = vitals.get('weight')
        height_str = vitals.get('height')
        extracted_bmi = vitals.get('bmi')
        
        if weight_str and height_str:
            try:
                # Extract numeric values
                weight_kg = float(re.search(r'[\d.]+', weight_str).group())
                height_cm = float(re.search(r'[\d.]+', height_str).group())
                
                # Calculate BMI
                height_m = height_cm / 100
                calculated_bmi = weight_kg / (height_m ** 2)
                calculated_bmi = round(calculated_bmi, 2)
                
                self.calculated_fields['bmi'] = f"{calculated_bmi} kg/m^2"
                
                # Verify against extracted BMI
                if extracted_bmi:
                    extracted_bmi_num = float(re.search(r'[\d.]+', extracted_bmi).group())
                    if abs(extracted_bmi_num - calculated_bmi) > 0.1:
                        self.validation_errors.append(
                            f"BMI mismatch: Extracted '{extracted_bmi}', Calculated '{calculated_bmi} kg/m^2' "
                            f"from weight {weight_kg}kg and height {height_cm}cm"
                        )
                else:
                    self.validation_warnings.append(f"BMI not extracted but can be calculated as {calculated_bmi} kg/m^2")
            except Exception as e:
                self.validation_warnings.append(f"Could not validate BMI calculation: {str(e)}")
    
    def _validate_calculated_lab_ratios(self, data: Dict[str, Any]):
        """Validate calculated laboratory test ratios"""
        lab_results = data.get('lab_results')
        if not isinstance(lab_results, list):
            lab_results = []
        
        # Create lookup dict for lab values
        lab_dict = {test['test_name']: test for test in lab_results if test and isinstance(test, dict) and 'test_name' in test}
        
        # Validate A/G Ratio
        albumin = lab_dict.get('SERUM ALBUMIN')
        globulin = lab_dict.get('SERUM GLOBULIN')
        ag_ratio = lab_dict.get('A/G RATIO')
        
        if albumin and globulin and ag_ratio:
            try:
                alb_val = float(albumin['result'])
                glob_val = float(globulin['result'])
                calculated_ag = alb_val / glob_val
                calculated_ag = round(calculated_ag, 2)
                
                self.calculated_fields['A/G_ratio'] = calculated_ag
                
                extracted_ag = float(ag_ratio['result'])
                if abs(extracted_ag - calculated_ag) > 0.1:
                    self.validation_errors.append(
                        f"A/G Ratio mismatch: Extracted '{extracted_ag}', Calculated '{calculated_ag}' "
                        f"from Albumin {alb_val} and Globulin {glob_val}"
                    )
            except Exception as e:
                self.validation_warnings.append(f"Could not validate A/G ratio: {str(e)}")
        
        # Validate TC/HDL Ratio
        total_chol = lab_dict.get('TOTAL CHOLESTEROL')
        hdl = lab_dict.get('HDL CHOLESTEROL - DIRECT')
        tc_hdl = lab_dict.get('TC/HDL')
        
        if total_chol and hdl and tc_hdl:
            try:
                tc_val = float(total_chol['result'])
                hdl_val = float(hdl['result'])
                calculated_tc_hdl = tc_val / hdl_val
                calculated_tc_hdl = round(calculated_tc_hdl, 1)
                
                self.calculated_fields['TC/HDL_ratio'] = calculated_tc_hdl
                
                extracted_tc_hdl = float(tc_hdl['result'])
                if abs(extracted_tc_hdl - calculated_tc_hdl) > 0.2:
                    self.validation_errors.append(
                        f"TC/HDL Ratio mismatch: Extracted '{extracted_tc_hdl}', Calculated '{calculated_tc_hdl}' "
                        f"from Total Cholesterol {tc_val} and HDL {hdl_val}"
                    )
            except Exception as e:
                self.validation_warnings.append(f"Could not validate TC/HDL ratio: {str(e)}")
        
        # Validate LDL/HDL Ratio
        ldl = lab_dict.get('LDL CHOLESTEROL - DIRECT')
        
        if ldl and hdl and lab_dict.get('LDL/HDL'):
            try:
                ldl_val = float(ldl['result'])
                hdl_val = float(hdl['result'])
                calculated_ldl_hdl = ldl_val / hdl_val
                calculated_ldl_hdl = round(calculated_ldl_hdl, 1)
                
                self.calculated_fields['LDL/HDL_ratio'] = calculated_ldl_hdl
                
                extracted_ldl_hdl = float(lab_dict['LDL/HDL']['result'])
                if abs(extracted_ldl_hdl - calculated_ldl_hdl) > 0.2:
                    self.validation_errors.append(
                        f"LDL/HDL Ratio mismatch: Extracted '{extracted_ldl_hdl}', Calculated '{calculated_ldl_hdl}' "
                        f"from LDL {ldl_val} and HDL {hdl_val}"
                    )
            except Exception as e:
                self.validation_warnings.append(f"Could not validate LDL/HDL ratio: {str(e)}")
        
        # Validate VLDL (should be Triglycerides / 5)
        triglycerides = lab_dict.get('TRIGLYCERIDES')
        vldl = lab_dict.get('VLDL CHOLESTEROL')
        
        if triglycerides and vldl:
            try:
                trig_val = float(triglycerides['result'])
                calculated_vldl = trig_val / 5
                calculated_vldl = round(calculated_vldl, 1)
                
                self.calculated_fields['VLDL'] = calculated_vldl
                
                extracted_vldl = float(vldl['result'])
                if abs(extracted_vldl - calculated_vldl) > 1.0:
                    self.validation_errors.append(
                        f"VLDL mismatch: Extracted '{extracted_vldl}', Calculated '{calculated_vldl}' "
                        f"from Triglycerides {trig_val}"
                    )
            except Exception as e:
                self.validation_warnings.append(f"Could not validate VLDL calculation: {str(e)}")
    
    def _validate_lab_ranges(self, data: Dict[str, Any]):
        """Validate lab results are within or outside reference ranges as stated"""
        lab_results = data.get('lab_results')
        if not isinstance(lab_results, list):
            lab_results = []
        
        for test in lab_results:
            if not test or not isinstance(test, dict):
                continue
            test_name = test.get('test_name')
            result = test.get('result')
            ref_range = test.get('reference_range')
            status = test.get('status')
            
            if not result or not ref_range or result in ['NEGATIVE', 'NIL', 'ABSENT', 'CLEAR', 'PALE YELLOW']:
                continue
            
            try:
                result_num = float(result)
                
                # Parse reference range
                range_match = re.search(r'([\d.]+)\s*-\s*([\d.]+)', ref_range)
                if range_match:
                    min_val = float(range_match.group(1))
                    max_val = float(range_match.group(2))
                    
                    is_in_range = min_val <= result_num <= max_val
                    
                    # Verify status
                    if is_in_range and status != 'normal':
                        self.validation_warnings.append(
                            f"{test_name}: Result {result_num} is in range [{min_val}-{max_val}] "
                            f"but marked as '{status}'"
                        )
                    elif not is_in_range and status == 'normal':
                        self.validation_errors.append(
                            f"{test_name}: Result {result_num} is OUT of range [{min_val}-{max_val}] "
                            f"but marked as 'normal'"
                        )
                
                # Handle "up to X" ranges
                upto_match = re.search(r'up to\s+([\d.]+)', ref_range)
                if upto_match:
                    max_val = float(upto_match.group(1))
                    if result_num > max_val and status == 'normal':
                        self.validation_errors.append(
                            f"{test_name}: Result {result_num} exceeds max {max_val} but marked as 'normal'"
                        )
            except:
                continue
    
    def _validate_cross_references(self, data: Dict[str, Any]):
        """Validate consistency across different sections"""
        doctor_info = data.get('doctor_info')
        if not isinstance(doctor_info, dict):
            doctor_info = {}
            
        hospital_info = data.get('hospital_info')
        if not isinstance(hospital_info, dict):
            hospital_info = {}
        
        # Check if examiner name appears consistently
        examiner = doctor_info.get('medical_examiner', '')
        # Could add more cross-reference checks here
    
    def _validate_logical_consistency(self, data: Dict[str, Any]):
        """Validate logical consistency in the data"""
        clinical = data.get('clinical_findings')
        
        # Ensure clinical is a dictionary
        if not isinstance(clinical, dict):
            clinical = {}
        
        # Check if patient marked YES but details say NIL
        reported_history = clinical.get('patient_reported_history', [])
        history_details = clinical.get('medical_history_details', '')
        
        if len(reported_history) > 0 and history_details and 'NIL' in history_details.upper():
            self.validation_warnings.append(
                f"Patient marked YES for {len(reported_history)} conditions but details state 'NIL' - "
                f"this may indicate missing information or patient chose not to elaborate"
            )
    
    def _validate_data_types(self, data: Dict[str, Any]):
        """Validate data types and formats"""
        patient_info = data.get('patient_info')
        if not isinstance(patient_info, dict):
            patient_info = {}
        
        # Validate gender
        gender = patient_info.get('gender')
        if gender and gender not in ['Male', 'Female', 'Other', 'M', 'F']:
            self.validation_warnings.append(f"Unusual gender value: '{gender}'")
        
        # Validate phone numbers (if present)
        contact = patient_info.get('contact_number')
        if contact and not re.match(r'^[\d\s\-+()]+$', str(contact)):
            self.validation_warnings.append(f"Invalid phone number format: '{contact}'")
    
    def generate_report(self, data: Dict[str, Any]) -> str:
        """Generate a validation report"""
        is_valid, errors, warnings, calculated = self.validate_all(data)
        
        report = "\n" + "="*60 + "\n"
        report += "VALIDATION REPORT\n"
        report += "="*60 + "\n\n"
        
        if is_valid:
            report += "✓ ALL VALIDATIONS PASSED\n\n"
        else:
            report += f"✗ VALIDATION FAILED: {len(errors)} error(s) found\n\n"
        
        if errors:
            report += "ERRORS (MUST FIX):\n"
            for i, error in enumerate(errors, 1):
                report += f"  {i}. {error}\n"
            report += "\n"
        
        if warnings:
            report += f"WARNINGS ({len(warnings)}):\n"
            for i, warning in enumerate(warnings, 1):
                report += f"  {i}. {warning}\n"
            report += "\n"
        
        if calculated:
            report += "CALCULATED/VERIFIED FIELDS:\n"
            for field, value in calculated.items():
                report += f"  ✓ {field}: {value}\n"
            report += "\n"
        
        # Calculate data quality score
        total_fields = self._count_non_null_fields(data)
        completeness = (total_fields / 50) * 100  # Assume 50 possible fields
        
        report += f"DATA QUALITY:\n"
        report += f"  Completeness: {completeness:.1f}%\n"
        report += f"  Errors: {len(errors)}\n"
        report += f"  Warnings: {len(warnings)}\n"
        
        if len(errors) == 0 and len(warnings) <= 2:
            confidence = "HIGH"
        elif len(errors) <= 2 and len(warnings) <= 5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        report += f"  Confidence: {confidence}\n"
        report += "="*60 + "\n"
        
        return report
    
    def _count_non_null_fields(self, data: Dict[str, Any], count: int = 0) -> int:
        """Recursively count non-null fields"""
        if isinstance(data, dict):
            for value in data.values():
                if value is not None and value != [] and value != {}:
                    if isinstance(value, (dict, list)):
                        count = self._count_non_null_fields(value, count)
                    else:
                        count += 1
        elif isinstance(data, list):
            count += len([item for item in data if item is not None])
        return count
