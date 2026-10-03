from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Lifetime stats
    total_points = Column(Integer, default=0)
    total_games = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    total_free_throws = Column(Integer, default=0)
    total_fouls_committed = Column(Integer, default=0)
    total_fouls_received = Column(Integer, default=0)

    # Relationships
    friendships_sent = relationship("Friendship", foreign_keys="Friendship.user_id", back_populates="user")
    friendships_received = relationship("Friendship", foreign_keys="Friendship.friend_id", back_populates="friend")
    team_memberships = relationship("TeamMember", back_populates="user")
    captained_teams = relationship("Team", back_populates="captain")
    referred_matches = relationship("Match", foreign_keys="Match.referee_id", back_populates="referee")
    match_events = relationship("MatchEvent", back_populates="player")


class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="friendships_sent")
    friend = relationship("User", foreign_keys=[friend_id], back_populates="friendships_received")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    join_code = Column(String(10), unique=True, index=True, nullable=False)
    captain_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    captain = relationship("User", back_populates="captained_teams")
    members = relationship("TeamMember", back_populates="team")
    team1_matches = relationship("Match", foreign_keys="Match.team1_id", back_populates="team1")
    team2_matches = relationship("Match", foreign_keys="Match.team2_id", back_populates="team2")


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    team1_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    team2_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    referee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, active, completed
    team1_score = Column(Integer, default=0)
    team2_score = Column(Integer, default=0)
    mvp_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    team1 = relationship("Team", foreign_keys=[team1_id], back_populates="team1_matches")
    team2 = relationship("Team", foreign_keys=[team2_id], back_populates="team2_matches")
    referee = relationship("User", foreign_keys=[referee_id], back_populates="referred_matches")
    events = relationship("MatchEvent", back_populates="match")
    mvp = relationship("User", foreign_keys=[mvp_id])


class MatchEvent(Base):
    __tablename__ = "match_events"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(20), nullable=False)  # 2pt, 3pt, ft, foul_given, foul_received
    target_player_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # for fouls
    timestamp = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="events")
    player = relationship("User", foreign_keys=[player_id], back_populates="match_events")
    target_player = relationship("User", foreign_keys=[target_player_id])
