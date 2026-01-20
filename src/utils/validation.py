"""
Validation System
Handles automatic and manual validation of participant submissions
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image
import pytesseract

from src.models.models import (
    Submission, Challenge, Participant, 
    SubmissionStatus, ChallengeType
)
from src.database.db import DatabaseManager

logger = logging.getLogger(__name__)

class ValidationSystem:
    """System for validating participant submissions"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.max_submissions_per_day = 3  # Configurable limit
    
    def validate_submission(self, submission_id: int) -> Dict[str, any]:
        """Perform automatic validation on a submission"""
        db = self.db_manager.get_session()
        try:
            submission = db.query(Submission).get(submission_id)
            if not submission:
                return {'valid': False, 'errors': ['Submission not found']}
            
            challenge = db.query(Challenge).get(submission.challenge_id)
            participant = db.query(Participant).get(submission.participant_id)
            
            validation_results = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'score': 0
            }
            
            # Basic validation checks
            basic_checks = self._perform_basic_validation(submission, challenge, participant)
            validation_results['errors'].extend(basic_checks['errors'])
            validation_results['warnings'].extend(basic_checks['warnings'])
            
            # Media validation (if media exists)
            if submission.media_path:
                media_checks = self._validate_media(submission, challenge)
                validation_results['errors'].extend(media_checks['errors'])
                validation_results['warnings'].extend(media_checks['warnings'])
                validation_results['score'] += media_checks['score']
            
            # Result validation
            result_checks = self._validate_result(submission, challenge)
            validation_results['errors'].extend(result_checks['errors'])
            validation_results['warnings'].extend(result_checks['warnings'])
            validation_results['score'] += result_checks['score']
            
            # Update validation status
            if not validation_results['errors']:
                submission.status = SubmissionStatus.PENDING  # Ready for manual review
                db.commit()
            else:
                submission.status = SubmissionStatus.REJECTED
                db.commit()
            
            validation_results['valid'] = len(validation_results['errors']) == 0
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating submission {submission_id}: {e}")
            return {'valid': False, 'errors': [str(e)]}
        finally:
            db.close()
    
    def _perform_basic_validation(self, submission, challenge, participant) -> Dict[str, List]:
        """Perform basic validation checks"""
        errors = []
        warnings = []
        
        # Check if challenge is active
        if not challenge.is_active:
            errors.append("Challenge is not active")
        
        # Check if challenge period is valid
        now = datetime.now()
        if now < challenge.start_date or now > challenge.end_date:
            errors.append("Submission outside challenge period")
        
        # Check submission frequency (prevent spam)
        db = self.db_manager.get_session()
        try:
            recent_submissions = db.query(Submission).filter(
                Submission.participant_id == participant.id,
                Submission.challenge_id == challenge.id,
                Submission.submission_date >= datetime.now() - timedelta(hours=24)
            ).count()
            
            if recent_submissions >= self.max_submissions_per_day:
                errors.append(f"Maximum {self.max_submissions_per_day} submissions per day exceeded")
        finally:
            db.close()
        
        # Check participant status
        if not participant.is_active:
            errors.append("Participant account is inactive")
        
        return {'errors': errors, 'warnings': warnings}
    
    def _validate_media(self, submission, challenge) -> Dict[str, any]:
        """Validate submitted media file"""
        errors = []
        warnings = []
        score = 0
        
        try:
            media_path = submission.media_path
            
            # Check file exists
            import os
            if not os.path.exists(media_path):
                errors.append("Media file not found")
                return {'errors': errors, 'warnings': warnings, 'score': score}
            
            # Validate file type
            file_extension = media_path.lower().split('.')[-1]
            expected_types = self._get_expected_media_types(challenge.challenge_type)
            
            if file_extension not in expected_types:
                warnings.append(f"Unexpected file type. Expected: {', '.join(expected_types)}")
            
            # For images, perform basic analysis
            if file_extension in ['jpg', 'jpeg', 'png']:
                image_analysis = self._analyze_image(media_path, challenge.challenge_type)
                errors.extend(image_analysis['errors'])
                warnings.extend(image_analysis['warnings'])
                score += image_analysis['score']
            
            # For videos, check duration and basic properties
            elif file_extension in ['mp4', 'mov', 'avi']:
                video_analysis = self._analyze_video(media_path)
                errors.extend(video_analysis['errors'])
                warnings.extend(video_analysis['warnings'])
                score += video_analysis['score']
            
        except Exception as e:
            logger.error(f"Media validation error: {e}")
            errors.append("Error processing media file")
        
        return {'errors': errors, 'warnings': warnings, 'score': min(score, 30)}
    
    def _validate_result(self, submission, challenge) -> Dict[str, any]:
        """Validate submission result value"""
        errors = []
        warnings = []
        score = 0
        
        result_value = submission.result_value
        challenge_type = challenge.challenge_type
        
        # Check if result exists
        if result_value is None:
            errors.append("Result value is required")
            return {'errors': errors, 'warnings': warnings, 'score': score}
        
        # Validate result range based on challenge type
        valid_ranges = {
            ChallengeType.PUSH_UPS: (1, 500),      # 1-500 reps
            ChallengeType.SQUATS: (1, 500),        # 1-500 reps
            ChallengeType.PLANK: (10, 3600),       # 10 seconds - 1 hour
            ChallengeType.RUNNING: (0.1, 100),     # 100m - 100km
            ChallengeType.STEPS: (100, 100000)     # 100 - 100,000 steps
        }
        
        min_val, max_val = valid_ranges.get(challenge_type, (0, float('inf')))
        
        if result_value < min_val:
            errors.append(f"Result too low. Minimum: {min_val}")
        elif result_value > max_val:
            errors.append(f"Result too high. Maximum: {max_val}")
        else:
            # Score based on result plausibility
            score = self._calculate_result_score(result_value, challenge_type)
        
        return {'errors': errors, 'warnings': warnings, 'score': min(score, 40)}
    
    def _get_expected_media_types(self, challenge_type: ChallengeType) -> List[str]:
        """Get expected media file types for challenge type"""
        type_mapping = {
            ChallengeType.PUSH_UPS: ['mp4', 'mov', 'avi'],
            ChallengeType.SQUATS: ['mp4', 'mov', 'avi'],
            ChallengeType.PLANK: ['mp4', 'mov', 'avi'],
            ChallengeType.RUNNING: ['jpg', 'jpeg', 'png', 'pdf'],
            ChallengeType.STEPS: ['jpg', 'jpeg', 'png', 'pdf']
        }
        return type_mapping.get(challenge_type, ['jpg', 'jpeg', 'png', 'mp4', 'mov'])
    
    def _analyze_image(self, image_path: str, challenge_type: ChallengeType) -> Dict[str, any]:
        """Analyze image for validity"""
        errors = []
        warnings = []
        score = 0
        
        try:
            # Open image
            image = Image.open(image_path)
            
            # Check image dimensions
            width, height = image.size
            if width < 200 or height < 200:
                warnings.append("Image resolution is low")
            else:
                score += 10
            
            # Check image format and quality
            if image.format not in ['JPEG', 'PNG']:
                warnings.append("Non-standard image format")
            else:
                score += 5
            
            # For running/steps challenges, try OCR to extract data
            if challenge_type in [ChallengeType.RUNNING, ChallengeType.STEPS]:
                ocr_result = self._extract_text_from_image(image_path)
                if ocr_result['text_found']:
                    score += 15
                    # Validate extracted numbers
                    numbers = re.findall(r'\d+(?:\.\d+)?', ocr_result['text'])
                    if numbers:
                        score += 5
                else:
                    warnings.append("Could not extract text from image")
            
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            errors.append("Error analyzing image")
        
        return {'errors': errors, 'warnings': warnings, 'score': min(score, 30)}
    
    def _analyze_video(self, video_path: str) -> Dict[str, any]:
        """Analyze video for validity"""
        errors = []
        warnings = []
        score = 0
        
        try:
            import cv2
            
            # Open video
            cap = cv2.VideoCapture(video_path)
            
            # Check if video opened successfully
            if not cap.isOpened():
                errors.append("Cannot open video file")
                return {'errors': errors, 'warnings': warnings, 'score': score}
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            
            # Check duration (should be reasonable for exercise videos)
            if duration < 2:
                warnings.append("Video too short")
            elif duration > 300:  # 5 minutes
                warnings.append("Video too long")
            else:
                score += 15
            
            # Check frame rate
            if 15 <= fps <= 60:
                score += 10
            else:
                warnings.append("Unusual frame rate")
            
            cap.release()
            
        except ImportError:
            warnings.append("Video analysis requires OpenCV")
        except Exception as e:
            logger.error(f"Video analysis error: {e}")
            errors.append("Error analyzing video")
        
        return {'errors': errors, 'warnings': warnings, 'score': min(score, 30)}
    
    def _extract_text_from_image(self, image_path: str) -> Dict[str, any]:
        """Extract text from image using OCR"""
        try:
            # This would require pytesseract installation
            # text = pytesseract.image_to_string(Image.open(image_path), lang='rus+eng')
            # For now, return placeholder
            return {'text_found': False, 'text': ''}
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return {'text_found': False, 'text': ''}
    
    def _calculate_result_score(self, result_value: float, challenge_type: ChallengeType) -> int:
        """Calculate score based on result plausibility"""
        # More realistic results get higher scores
        base_scores = {
            ChallengeType.PUSH_UPS: lambda x: min(20, max(5, x // 5)),
            ChallengeType.SQUATS: lambda x: min(20, max(5, x // 5)),
            ChallengeType.PLANK: lambda x: min(20, max(5, x // 30)),  # Score by minutes
            ChallengeType.RUNNING: lambda x: min(20, max(5, int(x * 2))),  # Score by km
            ChallengeType.STEPS: lambda x: min(20, max(5, x // 1000))  # Score by thousands
        }
        
        scorer = base_scores.get(challenge_type, lambda x: 10)
        return scorer(result_value)
    
    def bulk_validate_pending_submissions(self) -> Dict[str, int]:
        """Validate all pending submissions"""
        db = self.db_manager.get_session()
        try:
            pending_submissions = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).all()
            
            results = {'validated': 0, 'errors': 0, 'approved_auto': 0}
            
            for submission in pending_submissions:
                validation = self.validate_submission(submission.id)
                results['validated'] += 1
                
                if not validation['valid']:
                    results['errors'] += 1
                elif validation['score'] >= 70:  # High confidence threshold
                    submission.status = SubmissionStatus.APPROVED
                    results['approved_auto'] += 1
            
            db.commit()
            return results
            
        except Exception as e:
            logger.error(f"Bulk validation error: {e}")
            db.rollback()
            return {'validated': 0, 'errors': 0, 'approved_auto': 0}
        finally:
            db.close()
    
    def get_validation_report(self, submission_id: int) -> Dict[str, any]:
        """Get detailed validation report for a submission"""
        db = self.db_manager.get_session()
        try:
            submission = db.query(Submission).get(submission_id)
            challenge = db.query(Challenge).get(submission.challenge_id)
            participant = db.query(Participant).get(submission.participant_id)
            
            validation = self.validate_submission(submission_id)
            
            return {
                'submission_id': submission_id,
                'participant': participant.full_name,
                'challenge': challenge.name,
                'submission_date': submission.submission_date.isoformat(),
                'validation_result': validation,
                'recommendation': self._get_recommendation(validation)
            }
            
        except Exception as e:
            logger.error(f"Error generating validation report: {e}")
            return {}
        finally:
            db.close()
    
    def _get_recommendation(self, validation_result: Dict) -> str:
        """Get recommendation based on validation results"""
        if not validation_result['valid']:
            return "Отклонить - есть ошибки валидации"
        elif validation_result['score'] >= 80:
            return "Одобрить автоматически"
        elif validation_result['score'] >= 60:
            return "На ручную проверку"
        else:
            return "Требует дополнительной проверки"