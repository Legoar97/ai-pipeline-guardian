import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google.cloud import firestore
from google.auth import default
import logging

logger = logging.getLogger(__name__)

class FirestoreClient:
    def __init__(self):
        """Initialize Firestore client"""
        try:
            # Use default credentials
            credentials, project = default()
            self.db = firestore.Client(project=project, credentials=credentials)
            logger.info(f"Firestore client initialized for project {project}")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            self.db = None
    
    async def save_pipeline_analysis(self, analysis_data: Dict) -> bool:
        """Save pipeline analysis to Firestore"""
        if not self.db:
            return False
        
        try:
            # Add timestamp if not present
            if 'timestamp' not in analysis_data:
                analysis_data['timestamp'] = datetime.now()
            
            # Save to 'pipeline_analyses' collection
            doc_ref = self.db.collection('pipeline_analyses').document()
            doc_ref.set(analysis_data)
            logger.info(f"Saved analysis for pipeline {analysis_data.get('pipeline_id')}")
            return True
        except Exception as e:
            logger.error(f"Error saving to Firestore: {e}")
            return False
    
    async def save_error_pattern(self, error_type: str, error_details: Dict) -> bool:
        """Track error patterns for learning"""
        if not self.db:
            return False
        
        try:
            # Update error patterns collection
            doc_ref = self.db.collection('error_patterns').document(error_type)
            doc = doc_ref.get()
            
            if doc.exists:
                # Increment count
                doc_ref.update({
                    'count': firestore.Increment(1),
                    'last_seen': datetime.now(),
                    'examples': firestore.ArrayUnion([error_details])
                })
            else:
                # Create new pattern
                doc_ref.set({
                    'error_type': error_type,
                    'count': 1,
                    'first_seen': datetime.now(),
                    'last_seen': datetime.now(),
                    'examples': [error_details]
                })
            return True
        except Exception as e:
            logger.error(f"Error saving error pattern: {e}")
            return False
    
    async def get_dashboard_stats(self) -> Dict:
        """Get statistics for dashboard"""
        if not self.db:
            return self._get_default_stats()
        
        try:
            stats = {
                'total_pipelines': 0,
                'total_fixes': 0,
                'total_retries': 0,
                'total_mrs_created': 0,
                'error_categories': {},
                'recent_analyses': [],
                'daily_stats': [],
                'success_rate': 0,
                'avg_fix_time': 0,
                'time_saved_hours': 0
            }
            
            # Get total counts
            analyses = self.db.collection('pipeline_analyses').stream()
            
            for doc in analyses:
                data = doc.to_dict()
                stats['total_pipelines'] += 1
                
                if data.get('retry_success'):
                    stats['total_retries'] += 1
                
                if data.get('mr_created'):
                    stats['total_mrs_created'] += 1
                
                # Count error categories
                for analysis in data.get('analyses', []):
                    category = analysis.get('error_category', 'other')
                    stats['error_categories'][category] = stats['error_categories'].get(category, 0) + 1
                
                # Add to recent analyses (last 10)
                if len(stats['recent_analyses']) < 10:
                    stats['recent_analyses'].append({
                        'pipeline_id': data.get('pipeline_id'),
                        'project_name': data.get('project_name'),
                        'timestamp': data.get('timestamp'),
                        'status': 'fixed' if data.get('mr_created') or data.get('retry_success') else 'analyzed',
                        'error_types': [a.get('error_category') for a in data.get('analyses', [])]
                    })
            
            # Calculate success rate
            if stats['total_pipelines'] > 0:
                stats['success_rate'] = round((stats['total_retries'] + stats['total_mrs_created']) / stats['total_pipelines'] * 100, 1)
            
            # Calculate time saved (15 min per analysis, 30 min per fix)
            stats['time_saved_hours'] = round((stats['total_pipelines'] * 15 + stats['total_fixes'] * 30) / 60, 1)
            
            # Get daily stats for last 7 days
            stats['daily_stats'] = await self._get_daily_stats()
            
            # Get error patterns
            stats['error_patterns'] = await self._get_error_patterns()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return self._get_default_stats()
    
    async def _get_daily_stats(self) -> List[Dict]:
        """Get daily statistics for last 7 days"""
        if not self.db:
            return []
        
        try:
            daily_stats = []
            today = datetime.now().date()
            
            for i in range(7):
                day = today - timedelta(days=i)
                start = datetime.combine(day, datetime.min.time())
                end = datetime.combine(day, datetime.max.time())
                
                # Count analyses for this day
                count = 0
                fixes = 0
                
                analyses = self.db.collection('pipeline_analyses')\
                    .where('timestamp', '>=', start)\
                    .where('timestamp', '<=', end)\
                    .stream()
                
                for doc in analyses:
                    count += 1
                    data = doc.to_dict()
                    if data.get('mr_created') or data.get('retry_success'):
                        fixes += 1
                
                daily_stats.append({
                    'date': day.strftime('%Y-%m-%d'),
                    'day': day.strftime('%a'),
                    'analyses': count,
                    'fixes': fixes
                })
            
            daily_stats.reverse()  # Oldest to newest
            return daily_stats
            
        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return []
    
    async def _get_error_patterns(self) -> List[Dict]:
        """Get most common error patterns"""
        if not self.db:
            return []
        
        try:
            patterns = []
            docs = self.db.collection('error_patterns')\
                .order_by('count', direction=firestore.Query.DESCENDING)\
                .limit(5)\
                .stream()
            
            for doc in docs:
                data = doc.to_dict()
                patterns.append({
                    'type': data.get('error_type'),
                    'count': data.get('count', 0),
                    'last_seen': data.get('last_seen')
                })
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error getting error patterns: {e}")
            return []
    
    def _get_default_stats(self) -> Dict:
        """Default stats when Firestore is not available"""
        return {
            'total_pipelines': 0,
            'total_fixes': 0,
            'total_retries': 0,
            'total_mrs_created': 0,
            'error_categories': {},
            'recent_analyses': [],
            'daily_stats': [],
            'success_rate': 0,
            'avg_fix_time': 0,
            'time_saved_hours': 0,
            'error_patterns': []
        }
    
    async def cleanup_old_data(self, days: int = 30) -> int:
        """Clean up data older than specified days"""
        if not self.db:
            return 0
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = 0
            
            # Delete old analyses
            old_docs = self.db.collection('pipeline_analyses')\
                .where('timestamp', '<', cutoff_date)\
                .stream()
            
            for doc in old_docs:
                doc.reference.delete()
                deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old documents")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return 0