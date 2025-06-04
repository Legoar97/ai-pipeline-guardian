import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import statistics
import re

logger = logging.getLogger(__name__)

class AIPredictor:
    """
    AI-powered predictive analysis for GitLab pipelines
    Predicts failures BEFORE they happen based on historical patterns
    """
    
    def __init__(self):
        logger.info("AI Predictor initialized - Proactive failure prevention enabled")
        
        # Risk thresholds
        self.RISK_THRESHOLDS = {
            "low": 0.3,
            "medium": 0.5,
            "high": 0.7,
            "critical": 0.85
        }
        
        # Known risk patterns
        self.risk_patterns = {
            "late_night_deploy": {
                "hours": [0, 1, 2, 3, 4, 5],
                "risk_multiplier": 1.8,
                "reason": "Late night deployments have 80% higher failure rate"
            },
            "friday_deploy": {
                "weekday": 4,  # Friday
                "after_hour": 15,  # After 3 PM
                "risk_multiplier": 1.5,
                "reason": "Friday afternoon deployments are risky"
            },
            "rapid_commits": {
                "threshold": 10,  # commits in last hour
                "risk_multiplier": 1.6,
                "reason": "Rapid commits often introduce errors"
            },
            "long_duration": {
                "threshold_minutes": 30,
                "risk_multiplier": 1.7,
                "reason": "Long pipelines are more likely to timeout"
            },
            "monday_morning": {
                "weekday": 0,  # Monday
                "hours": [7, 8, 9],
                "risk_multiplier": 1.4,
                "reason": "Monday morning surge often causes resource issues"
            }
        }
    
    def analyze_failure_patterns(self, historical_pipelines: List[Dict]) -> Dict:
        """Analyze historical pipelines to detect failure patterns"""
        
        if not historical_pipelines:
            return {
                "total_analyzed": 0,
                "patterns": {},
                "insights": []
            }
        
        # Separate failed and successful pipelines
        failed = [p for p in historical_pipelines if p.get("status") == "failed"]
        successful = [p for p in historical_pipelines if p.get("status") == "success"]
        
        patterns = {
            "failure_rate": len(failed) / len(historical_pipelines) if historical_pipelines else 0,
            "total_pipelines": len(historical_pipelines),
            "failed_count": len(failed),
            "success_count": len(successful)
        }
        
        # Analyze failure reasons
        failure_reasons = {}
        for pipeline in failed:
            reason = pipeline.get("failureReason", "unknown")
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        patterns["failure_reasons"] = failure_reasons
        
        # Time-based patterns
        patterns["failure_by_hour"] = self._analyze_time_patterns(failed)
        patterns["failure_by_weekday"] = self._analyze_weekday_patterns(failed)
        
        # Duration patterns
        patterns["duration_analysis"] = self._analyze_duration_patterns(historical_pipelines)
        
        # Generate insights
        insights = self._generate_insights(patterns)
        
        return {
            "total_analyzed": len(historical_pipelines),
            "patterns": patterns,
            "insights": insights
        }
    
    def predict_failure_risk(self, 
                           current_pipeline: Dict,
                           historical_data: Dict,
                           recent_commits: int = 0) -> Dict:
        """
        Predict if a pipeline will fail based on current conditions and historical patterns
        Returns risk score (0-1) and preventive actions
        """
        
        risk_factors = []
        total_risk = 0.0
        
        # Check time-based risks
        current_time = datetime.now()
        hour = current_time.hour
        weekday = current_time.weekday()
        
        # Late night risk
        if hour in self.risk_patterns["late_night_deploy"]["hours"]:
            risk_factor = 0.3 * self.risk_patterns["late_night_deploy"]["risk_multiplier"]
            risk_factors.append({
                "factor": "late_night_deployment",
                "contribution": risk_factor,
                "reason": self.risk_patterns["late_night_deploy"]["reason"],
                "mitigation": "Consider postponing to business hours"
            })
            total_risk += risk_factor
        
        # Friday afternoon risk
        if (weekday == self.risk_patterns["friday_deploy"]["weekday"] and 
            hour >= self.risk_patterns["friday_deploy"]["after_hour"]):
            risk_factor = 0.25 * self.risk_patterns["friday_deploy"]["risk_multiplier"]
            risk_factors.append({
                "factor": "friday_deployment",
                "contribution": risk_factor,
                "reason": self.risk_patterns["friday_deploy"]["reason"],
                "mitigation": "Deploy on Monday morning instead"
            })
            total_risk += risk_factor
        
        # Monday morning risk
        if (weekday == self.risk_patterns["monday_morning"]["weekday"] and 
            hour in self.risk_patterns["monday_morning"]["hours"]):
            risk_factor = 0.2 * self.risk_patterns["monday_morning"]["risk_multiplier"]
            risk_factors.append({
                "factor": "monday_morning_surge",
                "contribution": risk_factor,
                "reason": self.risk_patterns["monday_morning"]["reason"],
                "mitigation": "Wait 1-2 hours for load to stabilize"
            })
            total_risk += risk_factor
        
        # Rapid commits risk
        if recent_commits > self.risk_patterns["rapid_commits"]["threshold"]:
            risk_factor = 0.3 * self.risk_patterns["rapid_commits"]["risk_multiplier"]
            risk_factors.append({
                "factor": "rapid_commits",
                "contribution": risk_factor,
                "reason": f"{recent_commits} commits in last hour - {self.risk_patterns['rapid_commits']['reason']}",
                "mitigation": "Review changes carefully, consider staged deployment"
            })
            total_risk += risk_factor
        
        # Historical failure rate
        if historical_data and "patterns" in historical_data:
            base_failure_rate = historical_data["patterns"].get("failure_rate", 0)
            if base_failure_rate > 0.3:
                risk_factor = base_failure_rate * 0.5
                risk_factors.append({
                    "factor": "high_historical_failure_rate",
                    "contribution": risk_factor,
                    "reason": f"Project has {base_failure_rate*100:.1f}% historical failure rate",
                    "mitigation": "Implement additional testing stages"
                })
                total_risk += risk_factor
        
        # Check for specific failure patterns in history
        if historical_data and "patterns" in historical_data:
            hour_failures = historical_data["patterns"].get("failure_by_hour", {})
            if str(hour) in hour_failures:
                hour_failure_rate = hour_failures[str(hour)] / max(historical_data.get("total_analyzed", 1), 1)
                if hour_failure_rate > 0.2:
                    risk_factor = hour_failure_rate * 0.3
                    risk_factors.append({
                        "factor": "high_failure_hour",
                        "contribution": risk_factor,
                        "reason": f"Pipelines at {hour}:00 fail {hour_failure_rate*100:.1f}% of the time",
                        "mitigation": "Schedule pipeline for different time"
                    })
                    total_risk += risk_factor
        
        # Normalize risk score to 0-1
        risk_score = min(total_risk, 1.0)
        
        # Determine risk level
        risk_level = "low"
        for level, threshold in sorted(self.RISK_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
            if risk_score >= threshold:
                risk_level = level
                break
        
        # Predict most likely failure type
        likely_failure = "unknown"
        prevention = "Monitor pipeline closely"
        
        if risk_factors:
            # Sort by contribution to find primary risk
            primary_risk = max(risk_factors, key=lambda x: x["contribution"])
            
            if "timeout" in primary_risk["factor"] or "duration" in primary_risk["factor"]:
                likely_failure = "timeout"
                prevention = "Increase job timeout to 2 hours"
            elif "rapid_commits" in primary_risk["factor"]:
                likely_failure = "syntax_error"
                prevention = "Run local tests before pushing"
            elif "monday_morning" in primary_risk["factor"]:
                likely_failure = "resource_exhaustion"
                prevention = "Increase runner resources or wait"
            else:
                likely_failure = "general_failure"
                prevention = primary_risk["mitigation"]
        
        return {
            "risk_score": round(risk_score, 3),
            "risk_level": risk_level,
            "likely_failure": likely_failure,
            "prevention": prevention,
            "confidence": self._calculate_confidence(historical_data),
            "risk_factors": risk_factors,
            "recommendation": self._get_recommendation(risk_score, risk_factors)
        }
    
    def _analyze_time_patterns(self, failed_pipelines: List[Dict]) -> Dict[str, int]:
        """Analyze failures by hour of day"""
        failures_by_hour = {}
        
        for pipeline in failed_pipelines:
            created_at = pipeline.get("createdAt")
            if created_at:
                try:
                    # Parse ISO format timestamp
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    hour = dt.hour
                    failures_by_hour[str(hour)] = failures_by_hour.get(str(hour), 0) + 1
                except:
                    pass
        
        return failures_by_hour
    
    def _analyze_weekday_patterns(self, failed_pipelines: List[Dict]) -> Dict[str, int]:
        """Analyze failures by day of week"""
        failures_by_weekday = {}
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        for pipeline in failed_pipelines:
            created_at = pipeline.get("createdAt")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    weekday = weekday_names[dt.weekday()]
                    failures_by_weekday[weekday] = failures_by_weekday.get(weekday, 0) + 1
                except:
                    pass
        
        return failures_by_weekday
    
    def _analyze_duration_patterns(self, pipelines: List[Dict]) -> Dict:
        """Analyze pipeline duration patterns"""
        durations = [p.get("duration", 0) for p in pipelines if p.get("duration")]
        
        if not durations:
            return {}
        
        return {
            "avg_duration_seconds": statistics.mean(durations),
            "median_duration_seconds": statistics.median(durations),
            "max_duration_seconds": max(durations),
            "long_pipelines": len([d for d in durations if d > 1800]),  # > 30 min
            "timeout_risk": len([d for d in durations if d > 3000]) / len(durations)  # > 50 min
        }
    
    def _generate_insights(self, patterns: Dict) -> List[str]:
        """Generate actionable insights from patterns"""
        insights = []
        
        # Failure rate insight
        failure_rate = patterns.get("failure_rate", 0)
        if failure_rate > 0.3:
            insights.append(f"⚠️ High failure rate: {failure_rate*100:.1f}% of pipelines fail")
        
        # Time-based insights
        failure_by_hour = patterns.get("failure_by_hour", {})
        if failure_by_hour:
            worst_hour = max(failure_by_hour.items(), key=lambda x: x[1])
            insights.append(f"🕐 Most failures occur at {worst_hour[0]}:00 ({worst_hour[1]} failures)")
        
        # Duration insights
        duration_analysis = patterns.get("duration_analysis", {})
        if duration_analysis.get("timeout_risk", 0) > 0.1:
            insights.append(f"⏱️ {duration_analysis['timeout_risk']*100:.1f}% of pipelines risk timeout")
        
        # Failure reason insights
        failure_reasons = patterns.get("failure_reasons", {})
        if failure_reasons:
            top_reason = max(failure_reasons.items(), key=lambda x: x[1])
            insights.append(f"🔍 Most common failure: {top_reason[0]} ({top_reason[1]} times)")
        
        return insights
    
    def _calculate_confidence(self, historical_data: Dict) -> float:
        """Calculate confidence in prediction based on data quality"""
        if not historical_data:
            return 0.5
        
        total_analyzed = historical_data.get("total_analyzed", 0)
        
        # More data = higher confidence
        if total_analyzed >= 100:
            return 0.9
        elif total_analyzed >= 50:
            return 0.8
        elif total_analyzed >= 20:
            return 0.7
        else:
            return 0.6
    
    def _get_recommendation(self, risk_score: float, risk_factors: List[Dict]) -> str:
        """Get actionable recommendation based on risk analysis"""
        if risk_score >= self.RISK_THRESHOLDS["critical"]:
            return "🚨 CRITICAL: Postpone deployment. Multiple high-risk factors detected."
        elif risk_score >= self.RISK_THRESHOLDS["high"]:
            return "⚠️ HIGH RISK: Consider delaying or implementing suggested mitigations."
        elif risk_score >= self.RISK_THRESHOLDS["medium"]:
            return "⚡ MEDIUM RISK: Proceed with caution. Monitor pipeline closely."
        else:
            return "✅ LOW RISK: Safe to proceed with deployment."
    
    def get_predictive_comment(self, prediction: Dict, project_name: str) -> str:
        """Generate a helpful comment for the predicted risk"""
        risk_score = prediction["risk_score"]
        risk_level = prediction["risk_level"]
        
        comment = f"""🔮 **AI Pipeline Prediction Alert**

**Project:** {project_name}
**Risk Level:** {risk_level.upper()} ({risk_score*100:.1f}%)
**Prediction:** {prediction['likely_failure'].replace('_', ' ').title()} likely

**🎯 Recommendation:**
{prediction['recommendation']}

**📊 Risk Factors:**"""
        
        for factor in prediction.get("risk_factors", []):
            comment += f"\n- **{factor['factor'].replace('_', ' ').title()}**: {factor['reason']}"
            comment += f"\n  → *Mitigation*: {factor['mitigation']}"
        
        comment += f"""

**💡 Suggested Action:**
{prediction['prevention']}

**🤖 Confidence:** {prediction['confidence']*100:.0f}%

---
*This prediction is based on analysis of historical pipeline data. Taking preventive action now can save debugging time later.*
"""
        
        return comment