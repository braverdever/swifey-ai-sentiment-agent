from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SentimentAnalysis(Base):
    __tablename__ = 'sentiment_analysis'
    
    id = sa.Column(sa.Integer, primary_key=True)
    conversation_id = sa.Column(sa.String(255), index=True)
    timestamp = sa.Column(sa.DateTime, default=datetime.utcnow)
    analysis_data = sa.Column(sa.JSON)
    last_message_time = sa.Column(sa.DateTime)
    persona_id = sa.Column(sa.String(255), index=True)

class QuestionFeedback(Base):
    __tablename__ = 'question_feedback'
    
    id = sa.Column(sa.Integer, primary_key=True)
    persona_id = sa.Column(sa.String(255), index=True)
    question = sa.Column(sa.Text)
    context = sa.Column(sa.Text)
    feedback_score = sa.Column(sa.Float)
    feedback_type = sa.Column(sa.String(50))
    feedback_details = sa.Column(sa.JSON)
    timestamp = sa.Column(sa.DateTime, default=datetime.utcnow)
    conversation_id = sa.Column(sa.String(255), index=True)

class PersonaLearningMetrics(Base):
    __tablename__ = 'persona_learning_metrics'
    
    id = sa.Column(sa.Integer, primary_key=True)
    persona_id = sa.Column(sa.String(255), index=True)
    metric_type = sa.Column(sa.String(50))
    metric_value = sa.Column(sa.Float)
    timestamp = sa.Column(sa.DateTime, default=datetime.utcnow)
    details = sa.Column(sa.JSON) 