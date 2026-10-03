from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, joinedload
from passlib.context import CryptContext
from database import init_db, get_db
from models import (
    User, Friendship, Team, TeamMember, Match, MatchEvent, RefereeRequest,
    OneOnOneMatch, OneOnOneEvent
)
from datetime import datetime
from contextlib import asynccontextmanager
import random
import string


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-this-in-production")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_join_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def calculate_stats(user: User):
    """Calculate professional stats for a user"""
    stats = {
        "sport": user.sport,
        "games_played": user.total_games,
        "wins": user.total_wins,
        "losses": user.total_losses,
        "win_rate": 0,
    }

    if user.total_games > 0:
        stats["win_rate"] = round((user.total_wins / user.total_games) * 100, 1)

    if user.sport == "basketball":
        stats.update({
            "points_per_game": round(user.total_points / user.total_games, 1) if user.total_games > 0 else 0,
            "assists_per_game": round(user.total_assists / user.total_games, 1) if user.total_games > 0 else 0,
            "rebounds_per_game": round(user.total_rebounds / user.total_games, 1) if user.total_games > 0 else 0,
            "fouls_per_game": round(user.total_fouls_committed / user.total_games, 1) if user.total_games > 0 else 0,
        })
    elif user.sport == "football":
        stats.update({
            "goals_per_game": round(user.total_goals / user.total_games, 1) if user.total_games > 0 else 0,
            "assists_per_game": round(user.total_assists / user.total_games, 1) if user.total_games > 0 else 0,
        })

    return stats


def calculate_shot_heatmap(user: User, db: Session):
    """Calculate shot location data for heat map visualization"""
    shot_data = db.query(MatchEvent).filter(
        MatchEvent.player_id == user.id,
        MatchEvent.event_type.in_(["2pt", "3pt"]),
        MatchEvent.shot_x.isnot(None),
        MatchEvent.shot_y.isnot(None)
    ).all()

    shots = [{"x": s.shot_x, "y": s.shot_y, "type": s.event_type} for s in shot_data]
    return shots


def calculate_match_performance(user: User, db: Session):
    """Calculate performance score (out of 10) for each match"""
    user_team_ids = [t.team_id for t in db.query(TeamMember).filter(TeamMember.user_id == user.id).all()]

    matches = db.query(Match).filter(
        (Match.team1_id.in_(user_team_ids)) | (Match.team2_id.in_(user_team_ids)),
        Match.status == "completed"
    ).order_by(Match.completed_at.desc()).limit(10).all()

    performance_data = []
    for match in matches:
        events = db.query(MatchEvent).filter(
            MatchEvent.match_id == match.id,
            MatchEvent.player_id == user.id
        ).all()

        points = 0
        assists = 0
        for event in events:
            if event.event_type == "2pt":
                points += 2
            elif event.event_type == "3pt":
                points += 3
            elif event.event_type == "goal":
                points += 1
            elif event.event_type == "assist":
                assists += 1

        # Calculate performance score out of 10
        if match.sport == "basketball":
            # Basketball: 30 points + 10 assists = 10 score
            score = min(10, round((points + assists) / 4, 1))
        else:
            # Football: 3 goals + 3 assists = 10 score
            score = min(10, round((points + assists) * 1.5, 1))

        performance_data.append({
            "match_id": match.id,
            "score": score,
            "points": points,
            "assists": assists
        })

    # Reverse to show oldest to newest in chart
    performance_data.reverse()
    return performance_data


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Calculate professional stats
    stats = calculate_stats(current_user)

    # Calculate match performance data
    performance_data = calculate_match_performance(current_user, db)

    # Calculate shot heat map data from both 1v1 and team matches
    # Get shots from 1v1 matches
    one_on_one_shots = db.query(OneOnOneEvent).filter(
        OneOnOneEvent.player_id == current_user.id,
        OneOnOneEvent.event_type.in_(["1pt", "2pt", "3pt"]),
        OneOnOneEvent.shot_x.isnot(None),
        OneOnOneEvent.shot_y.isnot(None)
    ).all()

    # Get shots from team matches
    team_shots = db.query(MatchEvent).filter(
        MatchEvent.player_id == current_user.id,
        MatchEvent.event_type.in_(["1pt", "2pt", "3pt"]),
        MatchEvent.shot_x.isnot(None),
        MatchEvent.shot_y.isnot(None)
    ).all()

    # Combine all shots
    all_shots = []
    for shot in one_on_one_shots:
        all_shots.append({
            "x": shot.shot_x,
            "y": shot.shot_y,
            "type": shot.event_type
        })
    for shot in team_shots:
        all_shots.append({
            "x": shot.shot_x,
            "y": shot.shot_y,
            "type": shot.event_type
        })

    one_pointers = [s for s in all_shots if s["type"] == "1pt"]
    two_pointers = [s for s in all_shots if s["type"] == "2pt"]
    three_pointers = [s for s in all_shots if s["type"] == "3pt"]
    shot_heatmap = all_shots

    # Get recent games from friends
    friend_ids = [f.friend_id for f in current_user.friendships_sent]
    friend_ids += [f.user_id for f in current_user.friendships_received]

    recent_matches = db.query(Match).filter(
        Match.status == "completed"
    ).order_by(Match.completed_at.desc()).limit(10).all()

    # Get user's teams
    user_teams = db.query(Team).join(TeamMember).filter(
        TeamMember.user_id == current_user.id
    ).all()

    # Get friends for ranking comparison
    friends = []
    for friendship in current_user.friendships_sent:
        if friendship.status == "accepted":
            friend = db.query(User).filter(User.id == friendship.friend_id).first()
            if friend:
                friends.append(friend)

    for friendship in current_user.friendships_received:
        if friendship.status == "accepted":
            friend = db.query(User).filter(User.id == friendship.user_id).first()
            if friend:
                friends.append(friend)

    # Calculate user's rank among friends (by wins only)
    all_users = friends + [current_user]
    sorted_by_wins = sorted(all_users, key=lambda u: u.total_wins, reverse=True)

    user_wins_rank = None

    for i, user in enumerate(sorted_by_wins, 1):
        if user.id == current_user.id:
            user_wins_rank = i
            break

    friend_rankings = {
        "wins_rank": user_wins_rank,
        "total_friends": len(friends)
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "stats": stats,
        "performance_data": performance_data,
        "shot_heatmap": shot_heatmap,
        "one_pointers": one_pointers,
        "two_pointers": two_pointers,
        "three_pointers": three_pointers,
        "recent_matches": recent_matches,
        "user_teams": user_teams,
        "friend_rankings": friend_rankings
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "User not found"
            })
        
        if not verify_password(password, user.password_hash):
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Invalid password"
            })
        
        request.session["user_id"] = user.id
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Login failed: {str(e)}"
        })


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    sport: str = Form("basketball"),
    db: Session = Depends(get_db)
):
    try:
        # Validate input
        if len(username) < 3:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Username must be at least 3 characters"
            })

        if len(password) < 6:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Password must be at least 6 characters"
            })

        if sport not in ["basketball", "football"]:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Invalid sport selection"
            })

        # Check if user exists
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Username already exists"
            })

        # Create user
        user = User(
            username=username,
            password_hash=get_password_hash(password),
            sport=sport
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Log in user
        request.session["user_id"] = user.id
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": f"Registration failed: {str(e)}"
        })


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/friends", response_class=HTMLResponse)
async def friends_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Get accepted friends
    friends = []
    for friendship in current_user.friendships_sent:
        if friendship.status == "accepted":
            friend = db.query(User).filter(User.id == friendship.friend_id).first()
            if friend:
                friends.append(friend)

    for friendship in current_user.friendships_received:
        if friendship.status == "accepted":
            friend = db.query(User).filter(User.id == friendship.user_id).first()
            if friend:
                friends.append(friend)

    # Get pending friend requests (incoming)
    pending_requests = []
    for friendship in current_user.friendships_received:
        if friendship.status == "pending":
            sender = db.query(User).filter(User.id == friendship.user_id).first()
            if sender:
                pending_requests.append({
                    "id": friendship.id,
                    "username": sender.username
                })

    # Get sent friend requests (outgoing)
    sent_requests = []
    for friendship in current_user.friendships_sent:
        if friendship.status == "pending":
            recipient = db.query(User).filter(User.id == friendship.friend_id).first()
            if recipient:
                sent_requests.append({
                    "id": friendship.id,
                    "username": recipient.username
                })

    # Calculate who was fouled the most by current user
    fouled_count = {}
    # From team matches
    team_fouls = db.query(MatchEvent).filter(
        MatchEvent.player_id == current_user.id,
        MatchEvent.event_type == "foul_given",
        MatchEvent.target_player_id.isnot(None)
    ).all()
    for foul in team_fouls:
        if foul.target_player_id not in fouled_count:
            fouled_count[foul.target_player_id] = 0
        fouled_count[foul.target_player_id] += 1

    # From 1v1 matches
    one_on_one_fouls = db.query(OneOnOneEvent).filter(
        OneOnOneEvent.player_id == current_user.id,
        OneOnOneEvent.event_type == "foul_given",
        OneOnOneEvent.target_player_id.isnot(None)
    ).all()
    for foul in one_on_one_fouls:
        if foul.target_player_id not in fouled_count:
            fouled_count[foul.target_player_id] = 0
        fouled_count[foul.target_player_id] += 1

    # Find most fouled player
    most_fouled_player = None
    most_fouled_count = 0
    for player_id, count in fouled_count.items():
        if count > most_fouled_count:
            most_fouled_count = count
            most_fouled_player = db.query(User).filter(User.id == player_id).first()

    # Calculate who received the most assists from current user
    assist_count = {}
    # From team matches
    team_assists = db.query(MatchEvent).filter(
        MatchEvent.player_id == current_user.id,
        MatchEvent.event_type == "assist",
        MatchEvent.target_player_id.isnot(None)
    ).all()
    for assist in team_assists:
        if assist.target_player_id not in assist_count:
            assist_count[assist.target_player_id] = 0
        assist_count[assist.target_player_id] += 1

    # From 1v1 matches (target_player_id might not exist in older records)
    try:
        one_on_one_assists = db.query(OneOnOneEvent).filter(
            OneOnOneEvent.player_id == current_user.id,
            OneOnOneEvent.event_type == "assist",
            OneOnOneEvent.target_player_id.isnot(None)
        ).all()
        for assist in one_on_one_assists:
            if assist.target_player_id not in assist_count:
                assist_count[assist.target_player_id] = 0
            assist_count[assist.target_player_id] += 1
    except:
        pass

    # Find most assisted player
    most_assisted_player = None
    most_assisted_count = 0
    for player_id, count in assist_count.items():
        if count > most_assisted_count:
            most_assisted_count = count
            most_assisted_player = db.query(User).filter(User.id == player_id).first()

    # Calculate 1v1 head-to-head records for each friend
    friend_records = {}
    for friend in friends:
        # Get completed 1v1 matches between current user and this friend
        matches = db.query(OneOnOneMatch).filter(
            OneOnOneMatch.status == "completed",
            ((OneOnOneMatch.player1_id == current_user.id) & (OneOnOneMatch.player2_id == friend.id)) |
            ((OneOnOneMatch.player1_id == friend.id) & (OneOnOneMatch.player2_id == current_user.id))
        ).all()

        user_wins = 0
        friend_wins = 0
        for match in matches:
            if match.winner_id == current_user.id:
                user_wins += 1
            elif match.winner_id == friend.id:
                friend_wins += 1

        friend_records[friend.id] = {
            "user_wins": user_wins,
            "friend_wins": friend_wins,
            "total_matches": len(matches)
        }

    return templates.TemplateResponse("friends.html", {
        "request": request,
        "user": current_user,
        "friends": friends,
        "pending_requests": pending_requests,
        "sent_requests": sent_requests,
        "most_fouled_player": most_fouled_player,
        "most_fouled_count": most_fouled_count,
        "most_assisted_player": most_assisted_player,
        "most_assisted_count": most_assisted_count,
        "friend_records": friend_records
    })


@app.post("/friends/add")
async def add_friend(
    request: Request,
    username: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    friend = db.query(User).filter(User.username == username).first()
    if not friend:
        return RedirectResponse(url="/friends?error=User not found", status_code=303)

    if friend.id == current_user.id:
        return RedirectResponse(url="/friends?error=Cannot add yourself", status_code=303)

    existing = db.query(Friendship).filter(
        ((Friendship.user_id == current_user.id) & (Friendship.friend_id == friend.id)) |
        ((Friendship.user_id == friend.id) & (Friendship.friend_id == current_user.id))
    ).first()

    if existing:
        return RedirectResponse(url="/friends?error=Request already sent or already friends", status_code=303)

    friendship = Friendship(user_id=current_user.id, friend_id=friend.id, status="pending")
    db.add(friendship)
    db.commit()

    return RedirectResponse(url="/friends", status_code=303)


@app.post("/friends/accept/{request_id}")
async def accept_friend_request(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    friendship = db.query(Friendship).filter(Friendship.id == request_id).first()
    if not friendship or friendship.friend_id != current_user.id:
        return RedirectResponse(url="/friends?error=Invalid request", status_code=303)

    friendship.status = "accepted"
    db.commit()

    return RedirectResponse(url="/friends", status_code=303)


@app.post("/friends/decline/{request_id}")
async def decline_friend_request(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    friendship = db.query(Friendship).filter(Friendship.id == request_id).first()
    if not friendship or friendship.friend_id != current_user.id:
        return RedirectResponse(url="/friends?error=Invalid request", status_code=303)

    db.delete(friendship)
    db.commit()

    return RedirectResponse(url="/friends", status_code=303)


@app.post("/friends/cancel/{request_id}")
async def cancel_friend_request(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    friendship = db.query(Friendship).filter(Friendship.id == request_id).first()
    if not friendship or friendship.user_id != current_user.id:
        return RedirectResponse(url="/friends?error=Invalid request", status_code=303)

    db.delete(friendship)
    db.commit()

    return RedirectResponse(url="/friends", status_code=303)


@app.get("/friends/{user_id}", response_class=HTMLResponse)
async def friend_profile(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Check if friends
    is_friend = db.query(Friendship).filter(
        ((Friendship.user_id == current_user.id) & (Friendship.friend_id == user_id)) |
        ((Friendship.user_id == user_id) & (Friendship.friend_id == current_user.id))
    ).first()

    if not is_friend:
        return RedirectResponse(url="/friends?error=Not friends with this user", status_code=303)

    friend = db.query(User).filter(User.id == user_id).first()

    # Get shot data for heat map from both team and 1v1 matches
    # From team matches
    team_shots = db.query(MatchEvent).filter(
        MatchEvent.player_id == user_id,
        MatchEvent.event_type.in_(["1pt", "2pt", "3pt"]),
        MatchEvent.shot_x.isnot(None),
        MatchEvent.shot_y.isnot(None)
    ).all()

    # From 1v1 matches
    one_on_one_shots = db.query(OneOnOneEvent).filter(
        OneOnOneEvent.player_id == user_id,
        OneOnOneEvent.event_type.in_(["1pt", "2pt", "3pt"]),
        OneOnOneEvent.shot_x.isnot(None),
        OneOnOneEvent.shot_y.isnot(None)
    ).all()

    # Combine all shots
    shots = []
    for shot in team_shots:
        shots.append({"x": shot.shot_x, "y": shot.shot_y, "type": shot.event_type})
    for shot in one_on_one_shots:
        shots.append({"x": shot.shot_x, "y": shot.shot_y, "type": shot.event_type})

    return templates.TemplateResponse("friend_profile.html", {
        "request": request,
        "user": current_user,
        "friend": friend,
        "shots": shots
    })


@app.get("/hall-of-fame", response_class=HTMLResponse)
async def hall_of_fame(
    request: Request,
    category: str = "wins",
    filter_type: str = "friends",
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Get all users based on filter (friends only)
    friend_ids = [f.friend_id for f in current_user.friendships_sent if f.status == "accepted"]
    friend_ids += [f.user_id for f in current_user.friendships_received if f.status == "accepted"]
    friend_ids.append(current_user.id)
    users = db.query(User).filter(User.id.in_(friend_ids)).all()

    # Sort based on category
    if category == "wins":
        sorted_users = sorted(users, key=lambda u: u.total_wins, reverse=True)
    elif category == "win_percentage":
        sorted_users = sorted(users, key=lambda u: (u.total_wins / u.total_games if u.total_games > 0 else 0), reverse=True)
    elif category == "three_pointers":
        sorted_users = sorted(users, key=lambda u: u.total_three_pointers_made, reverse=True)
    elif category == "games_played":
        sorted_users = sorted(users, key=lambda u: u.total_games, reverse=True)

    # Calculate user's rank
    user_rank = None
    for i, user in enumerate(sorted_users, 1):
        if user.id == current_user.id:
            user_rank = i
            break

    return templates.TemplateResponse("hall_of_fame.html", {
        "request": request,
        "current_user": current_user,
        "users": sorted_users,
        "category": category,
        "filter_type": filter_type,
        "user_rank": user_rank
    })


@app.get("/teams", response_class=HTMLResponse)
async def teams_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    user_teams = db.query(Team).join(TeamMember).filter(
        TeamMember.user_id == current_user.id
    ).all()

    return templates.TemplateResponse("teams.html", {
        "request": request,
        "user": current_user,
        "teams": user_teams
    })


@app.post("/teams/create")
async def create_team(
    request: Request,
    team_name: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    join_code = generate_join_code()
    while db.query(Team).filter(Team.join_code == join_code).first():
        join_code = generate_join_code()

    team = Team(
        name=team_name,
        join_code=join_code,
        captain_id=current_user.id,
        sport=current_user.sport
    )
    db.add(team)
    db.commit()
    db.refresh(team)

    team_member = TeamMember(team_id=team.id, user_id=current_user.id)
    db.add(team_member)
    db.commit()

    return RedirectResponse(url=f"/teams/{team.id}", status_code=303)


@app.post("/teams/join")
async def join_team(
    request: Request,
    join_code: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    team = db.query(Team).filter(Team.join_code == join_code.upper()).first()
    if not team:
        return RedirectResponse(url="/teams?error=Invalid team code", status_code=303)

    existing = db.query(TeamMember).filter(
        TeamMember.team_id == team.id,
        TeamMember.user_id == current_user.id
    ).first()

    if existing:
        return RedirectResponse(url="/teams?error=Already on this team", status_code=303)

    team_member = TeamMember(team_id=team.id, user_id=current_user.id)
    db.add(team_member)
    db.commit()

    return RedirectResponse(url=f"/teams/{team.id}", status_code=303)


@app.get("/teams/{team_id}", response_class=HTMLResponse)
async def team_detail(
    request: Request,
    team_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return RedirectResponse(url="/teams?error=Team not found", status_code=303)

    members = db.query(User).join(TeamMember).filter(
        TeamMember.team_id == team_id
    ).all()

    # Calculate team stats
    team_points = sum(m.total_points for m in members)
    team_wins = sum(m.total_wins for m in members)
    team_losses = sum(m.total_losses for m in members)

    return templates.TemplateResponse("team_detail.html", {
        "request": request,
        "user": current_user,
        "team": team,
        "members": members,
        "team_points": team_points,
        "team_wins": team_wins,
        "team_losses": team_losses
    })


@app.get("/challenge", response_class=HTMLResponse)
async def challenge_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Get user's teams (only captain can challenge)
    user_teams = db.query(Team).filter(Team.captain_id == current_user.id).all()

    # Get all teams for challenge target
    all_teams = db.query(Team).all()

    # Get friends
    friends = []
    for friendship in current_user.friendships_sent:
        if friendship.status == "accepted":
            friend = db.query(User).filter(User.id == friendship.friend_id).first()
            if friend:
                friends.append(friend)

    for friendship in current_user.friendships_received:
        if friendship.status == "accepted":
            friend = db.query(User).filter(User.id == friendship.user_id).first()
            if friend:
                friends.append(friend)

    # Get pending challenges (for teams the user is on)
    user_team_ids = [t.id for t in db.query(Team).join(TeamMember).filter(TeamMember.user_id == current_user.id).all()]
    pending_challenges = db.query(Match).filter(
        Match.team2_id.in_(user_team_ids),
        Match.status == "pending_challenge"
    ).all()

    # Get active matches (games in progress)
    active_matches = db.query(Match).filter(
        Match.status == "active"
    ).all()

    # Add team names to active matches
    for match in active_matches:
        team1 = db.query(Team).filter(Team.id == match.team1_id).first()
        team2 = db.query(Team).filter(Team.id == match.team2_id).first()
        if team1:
            match.team1_name = team1.name
        if team2:
            match.team2_name = team2.name

    # Get all teams for challenge target
    all_teams = db.query(Team).all()

    return templates.TemplateResponse("challenge.html", {
        "request": request,
        "user": current_user,
        "user_teams": user_teams,
        "all_teams": all_teams,
        "friends": friends,
        "pending_challenges": pending_challenges,
        "active_matches": active_matches
    })


@app.post("/challenge/create")
async def create_challenge(
    request: Request,
    team1_id: int = Form(...),
    team2_id: int = Form(...),
    referee_id: int = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    if team1_id == team2_id:
        return RedirectResponse(url="/challenge?error=Cannot challenge your own team", status_code=303)

    team1 = db.query(Team).filter(Team.id == team1_id).first()
    if not team1:
        return RedirectResponse(url="/challenge?error=Team not found", status_code=303)

    match = Match(
        team1_id=team1_id,
        team2_id=team2_id,
        referee_id=referee_id,
        sport=team1.sport,
        status="pending_challenge"
    )
    db.add(match)
    db.commit()
    db.refresh(match)

    # Create referee request
    referee_request = RefereeRequest(
        match_id=match.id,
        referee_id=referee_id,
        status="pending"
    )
    db.add(referee_request)
    db.commit()

    return RedirectResponse(url="/challenge", status_code=303)


@app.post("/challenge/accept/{match_id}")
async def accept_challenge(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse(url="/challenge?error=Match not found", status_code=303)

    # Check if user is on team2
    user_team_membership = db.query(TeamMember).filter(
        TeamMember.user_id == current_user.id,
        TeamMember.team_id == match.team2_id
    ).first()

    if not user_team_membership:
        return RedirectResponse(url="/challenge?error=Not authorized", status_code=303)

    match.status = "pending_referee"
    db.commit()

    return RedirectResponse(url="/challenge", status_code=303)


@app.post("/challenge/decline/{match_id}")
async def decline_challenge(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse(url="/challenge?error=Match not found", status_code=303)

    # Check if user is on team2
    user_team_membership = db.query(TeamMember).filter(
        TeamMember.user_id == current_user.id,
        TeamMember.team_id == match.team2_id
    ).first()

    if not user_team_membership:
        return RedirectResponse(url="/challenge?error=Not authorized", status_code=303)

    db.delete(match)
    db.commit()

    return RedirectResponse(url="/challenge", status_code=303)


@app.get("/refereeing", response_class=HTMLResponse)
async def refereeing_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Get pending referee requests
    pending_requests = db.query(RefereeRequest).filter(
        RefereeRequest.referee_id == current_user.id,
        RefereeRequest.status == "pending"
    ).all()

    # Get active matches the user is refereeing
    active_matches = db.query(Match).filter(
        Match.referee_id == current_user.id,
        Match.status == "active"
    ).all()

    # Get accepted matches ready to start
    accepted_matches = db.query(Match).filter(
        Match.referee_id == current_user.id,
        Match.status == "pending_referee"
    ).all()

    return templates.TemplateResponse("refereeing.html", {
        "request": request,
        "user": current_user,
        "pending_requests": pending_requests,
        "active_matches": active_matches,
        "accepted_matches": accepted_matches
    })


@app.post("/refereeing/accept/{request_id}")
async def accept_referee_request(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    referee_request = db.query(RefereeRequest).filter(RefereeRequest.id == request_id).first()
    if not referee_request or referee_request.referee_id != current_user.id:
        return RedirectResponse(url="/refereeing?error=Invalid request", status_code=303)

    referee_request.status = "accepted"
    referee_request.match.status = "pending_referee"
    db.commit()

    return RedirectResponse(url="/refereeing", status_code=303)


@app.post("/refereeing/decline/{request_id}")
async def decline_referee_request(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    referee_request = db.query(RefereeRequest).filter(RefereeRequest.id == request_id).first()
    if not referee_request or referee_request.referee_id != current_user.id:
        return RedirectResponse(url="/refereeing?error=Invalid request", status_code=303)

    referee_request.status = "declined"
    db.commit()

    return RedirectResponse(url="/refereeing", status_code=303)


@app.get("/match/{match_id}", response_class=HTMLResponse)
async def match_detail(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse(url="/", status_code=303)

    team1 = db.query(Team).filter(Team.id == match.team1_id).first()
    team2 = db.query(Team).filter(Team.id == match.team2_id).first()
    referee = db.query(User).filter(User.id == match.referee_id).first()

    team1_members = db.query(User).join(TeamMember).filter(
        TeamMember.team_id == match.team1_id
    ).all()

    team2_members = db.query(User).join(TeamMember).filter(
        TeamMember.team_id == match.team2_id
    ).all()

    # Get events for timeline and score progression
    events = db.query(MatchEvent).filter(MatchEvent.match_id == match_id).order_by(MatchEvent.timestamp).all()

    # Calculate score progression over time
    score_progression = []
    team1_score = 0
    team2_score = 0
    event_count = 0

    for event in events:
        event_count += 1
        if match.sport == "basketball":
            if event.event_type in ["2pt", "3pt"]:
                team_membership = db.query(TeamMember).filter(TeamMember.user_id == event.player_id).first()
                if team_membership:
                    points = int(event.event_type[0])
                    if team_membership.team_id == match.team1_id:
                        team1_score += points
                    else:
                        team2_score += points
        elif match.sport == "football":
            if event.event_type == "goal":
                team_membership = db.query(TeamMember).filter(TeamMember.user_id == event.player_id).first()
                if team_membership:
                    if team_membership.team_id == match.team1_id:
                        team1_score += 1
                    else:
                        team2_score += 1

        score_progression.append({
            "event": event_count,
            "team1_score": team1_score,
            "team2_score": team2_score
        })

    return templates.TemplateResponse("match_detail.html", {
        "request": request,
        "user": current_user,
        "match": match,
        "team1": team1,
        "team2": team2,
        "referee": referee,
        "team1_members": team1_members,
        "team2_members": team2_members,
        "events": events,
        "score_progression": score_progression
    })


@app.post("/match/{match_id}/start")
async def start_match(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match or match.referee_id != current_user.id:
        return RedirectResponse(url=f"/refereeing?error=Not authorized", status_code=303)

    match.status = "active"
    match.started_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/referee/{match_id}", status_code=303)


@app.get("/referee/{match_id}", response_class=HTMLResponse)
async def referee_dashboard(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Try to find as team match first
    match = db.query(Match).filter(Match.id == match_id).first()
    if match and match.referee_id == current_user.id:
        # Team match
        team1 = db.query(Team).filter(Team.id == match.team1_id).first()
        team2 = db.query(Team).filter(Team.id == match.team2_id).first()

        team1_members = db.query(User).join(TeamMember).filter(
            TeamMember.team_id == match.team1_id
        ).all()

        team2_members = db.query(User).join(TeamMember).filter(
            TeamMember.team_id == match.team2_id
        ).all()

        return templates.TemplateResponse("referee.html", {
            "request": request,
            "user": current_user,
            "match": match,
            "team1": team1,
            "team2": team2,
            "team1_members": team1_members,
            "team2_members": team2_members
        })

    # Try to find as 1v1 match
    one_on_one_match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if one_on_one_match:
        # Check if user is authorized (for 1v1, both players can referee)
        if current_user.id not in [one_on_one_match.player1_id, one_on_one_match.player2_id]:
            return RedirectResponse(url="/", status_code=303)

        player1 = db.query(User).filter(User.id == one_on_one_match.player1_id).first()
        player2 = db.query(User).filter(User.id == one_on_one_match.player2_id).first()

        return templates.TemplateResponse("referee.html", {
            "request": request,
            "user": current_user,
            "match": one_on_one_match,
            "team1": None,
            "team2": None,
            "team1_members": [],
            "team2_members": [],
            "player1": player1,
            "player2": player2
        })

    return RedirectResponse(url="/", status_code=303)


@app.post("/referee/event")
async def record_event(
    request: Request,
    match_id: int = Form(...),
    player_id: int = Form(...),
    event_type: str = Form(...),
    target_player_id: int = Form(None),
    shot_x: int = Form(None),
    shot_y: int = Form(None),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return {"error": "Not authenticated"}

    # Try team match first
    match = db.query(Match).filter(Match.id == match_id).first()
    if match:
        if match.referee_id != current_user.id:
            return {"error": "Not authorized"}

        event = MatchEvent(
            match_id=match_id,
            player_id=player_id,
            event_type=event_type,
            target_player_id=target_player_id,
            shot_x=shot_x,
            shot_y=shot_y
        )
        db.add(event)

        # Update match score based on sport and event type
        if match.sport == "basketball":
            if event_type in ["1pt", "2pt", "3pt", "ft"]:
                points = int(event_type[0]) if event_type != "ft" else 1
                player = db.query(User).filter(User.id == player_id).first()
                team_membership = db.query(TeamMember).filter(
                    TeamMember.user_id == player_id
                ).first()

                if team_membership:
                    if team_membership.team_id == match.team1_id:
                        match.team1_score += points
                    elif team_membership.team_id == match.team2_id:
                        match.team2_score += points
            elif event_type == "assist":
                # Assists don't affect score
                pass
            elif event_type == "rebound":
                # Rebounds don't affect score
                pass
            elif event_type == "foul_given":
                # Fouls don't affect score
                pass
        elif match.sport == "football":
            if event_type == "goal":
                player = db.query(User).filter(User.id == player_id).first()
                team_membership = db.query(TeamMember).filter(
                    TeamMember.user_id == player_id
                ).first()

                if team_membership:
                    if team_membership.team_id == match.team1_id:
                        match.team1_score += 1
                    elif team_membership.team_id == match.team2_id:
                        match.team2_score += 1

        db.commit()

        return {
            "success": True,
            "team1_score": match.team1_score,
            "team2_score": match.team2_score
        }

    # Try 1v1 match
    one_on_one_match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if one_on_one_match:
        if current_user.id not in [one_on_one_match.player1_id, one_on_one_match.player2_id]:
            return {"error": "Not authorized"}

        event = OneOnOneEvent(
            match_id=match_id,
            player_id=player_id,
            event_type=event_type,
            shot_x=shot_x,
            shot_y=shot_y
        )
        db.add(event)

        # Update score based on sport and event type
        if one_on_one_match.sport == "basketball":
            if event_type in ["1pt", "2pt", "3pt", "ft"]:
                points = int(event_type[0]) if event_type != "ft" else 1
                if player_id == one_on_one_match.player1_id:
                    one_on_one_match.player1_score += points
                else:
                    one_on_one_match.player2_score += points
        elif one_on_one_match.sport == "football":
            if event_type == "goal":
                if player_id == one_on_one_match.player1_id:
                    one_on_one_match.player1_score += 1
                else:
                    one_on_one_match.player2_score += 1

        db.commit()

        return {
            "success": True,
            "player1_score": one_on_one_match.player1_score,
            "player2_score": one_on_one_match.player2_score
        }

    return {"error": "Match not found"}


@app.get("/match/{match_id}/scoreboard", response_class=HTMLResponse)
async def scoreboard(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse(url="/", status_code=303)

    team1 = db.query(Team).filter(Team.id == match.team1_id).first()
    team2 = db.query(Team).filter(Team.id == match.team2_id).first()

    return templates.TemplateResponse("scoreboard.html", {
        "request": request,
        "user": current_user,
        "match": match,
        "team1": team1,
        "team2": team2
    })


@app.get("/api/match/{match_id}/score")
async def get_match_score(match_id: int, db: Session = Depends(get_db)):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return {"error": "Match not found"}

    return {
        "team1_score": match.team1_score,
        "team2_score": match.team2_score,
        "status": match.status
    }


@app.post("/match/{match_id}/end")
async def end_match(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match or match.referee_id != current_user.id:
        return RedirectResponse(url=f"/match/{match_id}?error=Not authorized", status_code=303)

    match.status = "completed"
    match.completed_at = datetime.utcnow()

    # Get all events for this match
    events = db.query(MatchEvent).filter(MatchEvent.match_id == match_id).all()

    # Calculate player stats and update profiles based on sport
    player_stats = {}
    for event in events:
        if event.player_id not in player_stats:
            player_stats[event.player_id] = {
                "points": 0,
                "assists": 0,
                "goals": 0,
                "rebounds": 0,
                "fouls_committed": 0,
                "fouls_received": 0,
                "fouled_players": {},  # Track who this player fouled
                "assisted_players": {}  # Track who this player assisted
            }

        if match.sport == "basketball":
            if event.event_type == "1pt":
                player_stats[event.player_id]["points"] += 1
            elif event.event_type == "2pt":
                player_stats[event.player_id]["points"] += 2
            elif event.event_type == "3pt":
                player_stats[event.player_id]["points"] += 3
            elif event.event_type == "assist":
                player_stats[event.player_id]["assists"] += 1
                if event.target_player_id:
                    if event.target_player_id not in player_stats[event.player_id]["assisted_players"]:
                        player_stats[event.player_id]["assisted_players"][event.target_player_id] = 0
                    player_stats[event.player_id]["assisted_players"][event.target_player_id] += 1
            elif event.event_type == "rebound":
                player_stats[event.player_id]["rebounds"] = player_stats[event.player_id].get("rebounds", 0) + 1
            elif event.event_type == "foul_given":
                player_stats[event.player_id]["fouls_committed"] += 1
                if event.target_player_id:
                    if event.target_player_id not in player_stats[event.player_id]["fouled_players"]:
                        player_stats[event.player_id]["fouled_players"][event.target_player_id] = 0
                    player_stats[event.player_id]["fouled_players"][event.target_player_id] += 1
                    # Track fouls received for the target
                    if event.target_player_id not in player_stats:
                        player_stats[event.target_player_id] = {
                            "points": 0,
                            "assists": 0,
                            "goals": 0,
                            "rebounds": 0,
                            "fouls_committed": 0,
                            "fouls_received": 0,
                            "fouled_players": {},
                            "assisted_players": {}
                        }
                    player_stats[event.target_player_id]["fouls_received"] += 1
        elif match.sport == "football":
            if event.event_type == "goal":
                player_stats[event.player_id]["goals"] += 1
                player_stats[event.player_id]["points"] += 1
            elif event.event_type == "assist":
                player_stats[event.player_id]["assists"] += 1
                if event.target_player_id:
                    if event.target_player_id not in player_stats[event.player_id]["assisted_players"]:
                        player_stats[event.player_id]["assisted_players"][event.target_player_id] = 0
                    player_stats[event.player_id]["assisted_players"][event.target_player_id] += 1
            elif event.event_type == "foul_given":
                player_stats[event.player_id]["fouls_committed"] += 1
                if event.target_player_id:
                    if event.target_player_id not in player_stats[event.player_id]["fouled_players"]:
                        player_stats[event.player_id]["fouled_players"][event.target_player_id] = 0
                    player_stats[event.player_id]["fouled_players"][event.target_player_id] += 1
                    if event.target_player_id not in player_stats:
                        player_stats[event.target_player_id] = {
                            "points": 0,
                            "assists": 0,
                            "goals": 0,
                            "rebounds": 0,
                            "fouls_committed": 0,
                            "fouls_received": 0,
                            "fouled_players": {},
                            "assisted_players": {}
                        }
                    player_stats[event.target_player_id]["fouls_received"] += 1

    # Find MVP (player with most points/goals)
    mvp_id = None
    max_score = 0
    for player_id, stats in player_stats.items():
        if stats["points"] > max_score:
            max_score = stats["points"]
            mvp_id = player_id

    match.mvp_id = mvp_id

    # Update user profiles
    for player_id, stats in player_stats.items():
        user = db.query(User).filter(User.id == player_id).first()
        if user:
            user.total_points += stats["points"]
            user.total_assists += stats["assists"]
            user.total_goals += stats["goals"]
            user.total_rebounds += stats.get("rebounds", 0)
            user.total_fouls_committed += stats["fouls_committed"]
            user.total_fouls_received += stats["fouls_received"]
            user.total_games += 1

            # Track 3-pointers made
            if match.sport == "basketball":
                user_events = [e for e in events if e.player_id == player_id]
                three_pointers = sum(1 for e in user_events if e.event_type == "3pt")
                user.total_three_pointers += three_pointers
                user.total_three_pointers_made += three_pointers

    # Flush to ensure all changes are written
    db.flush()

    # Update wins/losses
    if match.team1_score > match.team2_score:
        team1_members = db.query(TeamMember).filter(TeamMember.team_id == match.team1_id).all()
        team2_members = db.query(TeamMember).filter(TeamMember.team_id == match.team2_id).all()

        for member in team1_members:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user:
                user.total_wins += 1

        for member in team2_members:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user:
                user.total_losses += 1
    else:
        team1_members = db.query(TeamMember).filter(TeamMember.team_id == match.team1_id).all()
        team2_members = db.query(TeamMember).filter(TeamMember.team_id == match.team2_id).all()

        for member in team2_members:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user:
                user.total_wins += 1

        for member in team1_members:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user:
                user.total_losses += 1

    db.commit()

    return RedirectResponse(url=f"/match/{match_id}", status_code=303)


@app.get("/match/{match_id}/scoreboard", response_class=HTMLResponse)
async def match_scoreboard(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return RedirectResponse(url="/", status_code=303)

    team1 = db.query(Team).filter(Team.id == match.team1_id).first()
    team2 = db.query(Team).filter(Team.id == match.team2_id).first()

    team1_members = db.query(User).join(TeamMember).filter(
        TeamMember.team_id == match.team1_id
    ).all()

    team2_members = db.query(User).join(TeamMember).filter(
        TeamMember.team_id == match.team2_id
    ).all()

    # Get live player stats from events
    player_stats = {}
    events = db.query(MatchEvent).filter(MatchEvent.match_id == match_id).all()

    for event in events:
        if event.player_id not in player_stats:
            player_stats[event.player_id] = {
                "points": 0,
                "assists": 0,
                "goals": 0
            }

        if event.event_type in ["2pt", "3pt", "goal"]:
            if event.event_type == "2pt":
                player_stats[event.player_id]["points"] += 2
            elif event.event_type == "3pt":
                player_stats[event.player_id]["points"] += 3
            elif event.event_type == "goal":
                player_stats[event.player_id]["points"] += 1
                player_stats[event.player_id]["goals"] += 1
        elif event.event_type == "assist":
            player_stats[event.player_id]["assists"] += 1

    return templates.TemplateResponse("scoreboard.html", {
        "request": request,
        "match": match,
        "team1": team1,
        "team2": team2,
        "team1_members": team1_members,
        "team2_members": team2_members,
        "player_stats": player_stats
    })


# ============ 1v1 Routes ============

@app.get("/1v1", response_class=HTMLResponse)
async def one_on_one_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    # Get friendships with eager loading
    friendships_sent = db.query(Friendship).filter(
        Friendship.user_id == current_user.id
    ).options(
        joinedload(Friendship.friend)
    ).all()

    friendships_received = db.query(Friendship).filter(
        Friendship.friend_id == current_user.id
    ).options(
        joinedload(Friendship.user)
    ).all()

    # Get friends
    friends = []
    for friendship in friendships_sent:
        if friendship.status == "accepted" and friendship.friend:
            friends.append(friendship.friend)

    for friendship in friendships_received:
        if friendship.status == "accepted" and friendship.user:
            friends.append(friendship.user)

    # Get pending 1v1 challenges
    pending_challenges = db.query(OneOnOneMatch).filter(
        OneOnOneMatch.player2_id == current_user.id,
        OneOnOneMatch.status == "pending"
    ).options(
        joinedload(OneOnOneMatch.player1),
        joinedload(OneOnOneMatch.player2)
    ).all()

    # Get active 1v1 matches
    active_matches = db.query(OneOnOneMatch).filter(
        OneOnOneMatch.status == "active"
    ).options(
        joinedload(OneOnOneMatch.player1),
        joinedload(OneOnOneMatch.player2)
    ).all()

    # Get completed 1v1 matches
    completed_matches = db.query(OneOnOneMatch).filter(
        OneOnOneMatch.status == "completed"
    ).options(
        joinedload(OneOnOneMatch.player1),
        joinedload(OneOnOneMatch.player2)
    ).order_by(OneOnOneMatch.completed_at.desc()).limit(10).all()

    return templates.TemplateResponse("one_on_one.html", {
        "request": request,
        "user": current_user,
        "friends": friends,
        "pending_challenges": pending_challenges,
        "active_matches": active_matches,
        "completed_matches": completed_matches
    })


@app.post("/1v1/challenge")
async def create_one_on_one_challenge(
    request: Request,
    opponent_id: int = Form(...),
    sport: str = Form(...),
    scoring_type: str = Form("twos"),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    if opponent_id == current_user.id:
        return RedirectResponse(url="/1v1?error=Cannot challenge yourself", status_code=303)

    opponent = db.query(User).filter(User.id == opponent_id).first()
    if not opponent:
        return RedirectResponse(url="/1v1?error=User not found", status_code=303)

    match = OneOnOneMatch(
        player1_id=current_user.id,
        player2_id=opponent_id,
        sport=sport,
        scoring_type=scoring_type,
        status="pending"
    )
    db.add(match)
    db.commit()

    return RedirectResponse(url="/1v1", status_code=303)


@app.post("/1v1/accept/{match_id}")
async def accept_one_on_one_challenge(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if not match or match.player2_id != current_user.id:
        return RedirectResponse(url="/1v1?error=Invalid challenge", status_code=303)

    match.status = "active"
    match.started_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/referee/{match_id}", status_code=303)


@app.post("/1v1/{match_id}/start")
async def start_one_on_one_match(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if not match:
        return RedirectResponse(url="/1v1?error=Match not found", status_code=303)

    # Only players in the match can start it
    if current_user.id not in [match.player1_id, match.player2_id]:
        return RedirectResponse(url=f"/1v1?error=Not authorized", status_code=303)

    match.status = "active"
    match.started_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/referee/{match_id}", status_code=303)
    if not match or match.player2_id != current_user.id:
        return RedirectResponse(url="/1v1?error=Invalid challenge", status_code=303)

    match.status = "active"
    match.started_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/1v1/{match_id}/referee", status_code=303)


@app.post("/1v1/decline/{match_id}")
async def decline_one_on_one_challenge(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if not match or match.player2_id != current_user.id:
        return RedirectResponse(url="/1v1?error=Invalid challenge", status_code=303)

    db.delete(match)
    db.commit()

    return RedirectResponse(url="/1v1", status_code=303)


@app.get("/1v1/{match_id}", response_class=HTMLResponse)
async def one_on_one_detail(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).options(
        joinedload(OneOnOneMatch.player1),
        joinedload(OneOnOneMatch.player2)
    ).first()
    if not match:
        return RedirectResponse(url="/1v1", status_code=303)

    events = db.query(OneOnOneEvent).filter(
        OneOnOneEvent.match_id == match_id
    ).options(
        joinedload(OneOnOneEvent.player)
    ).order_by(OneOnOneEvent.timestamp).all()

    return templates.TemplateResponse("one_on_one_detail.html", {
        "request": request,
        "user": current_user,
        "match": match,
        "player1": match.player1,
        "player2": match.player2,
        "events": events
    })


@app.get("/1v1/{match_id}/referee", response_class=HTMLResponse)
async def one_on_one_referee(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    # Redirect to unified referee dashboard
    return RedirectResponse(url=f"/referee/{match_id}", status_code=303)


@app.post("/1v1/event")
async def record_one_on_one_event(
    request: Request,
    match_id: int = Form(...),
    player_id: int = Form(...),
    event_type: str = Form(...),
    target_player_id: int = Form(None),
    shot_x: int = Form(None),
    shot_y: int = Form(None),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return {"error": "Not authenticated"}

    match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if not match:
        return {"error": "Match not found"}

    # Only players in the match can record events
    if current_user.id not in [match.player1_id, match.player2_id]:
        return {"error": "Not authorized"}

    event = OneOnOneEvent(
        match_id=match_id,
        player_id=player_id,
        event_type=event_type,
        target_player_id=target_player_id,
        shot_x=shot_x,
        shot_y=shot_y
    )
    db.add(event)

    # Update score based on sport and event type
    if match.sport == "basketball":
        if event_type in ["1pt", "2pt", "3pt", "ft"]:
            points = int(event_type[0]) if event_type != "ft" else 1
            if player_id == match.player1_id:
                match.player1_score += points
            else:
                match.player2_score += points
    elif match.sport == "football":
        if event_type == "goal":
            if player_id == match.player1_id:
                match.player1_score += 1
            else:
                match.player2_score += 1

    db.commit()

    return {
        "success": True,
        "player1_score": match.player1_score,
        "player2_score": match.player2_score
    }


@app.post("/1v1/{match_id}/end")
async def end_one_on_one_match(
    request: Request,
    match_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    match = db.query(OneOnOneMatch).filter(OneOnOneMatch.id == match_id).first()
    if not match:
        return RedirectResponse(url="/1v1?error=Match not found", status_code=303)

    # Only players in the match can end it
    if current_user.id not in [match.player1_id, match.player2_id]:
        return RedirectResponse(url="/1v1?error=Not authorized", status_code=303)

    match.status = "completed"
    match.completed_at = datetime.utcnow()

    # Determine winner
    if match.player1_score > match.player2_score:
        match.winner_id = match.player1_id
    elif match.player2_score > match.player1_score:
        match.winner_id = match.player2_id

    # Get all events for stats calculation
    events = db.query(OneOnOneEvent).filter(OneOnOneEvent.match_id == match_id).all()

    # Calculate player stats including fouls
    player1_stats = {
        "points": 0,
        "rebounds": 0,
        "fouls_committed": 0,
        "fouls_received": 0
    }
    player2_stats = {
        "points": 0,
        "rebounds": 0,
        "fouls_committed": 0,
        "fouls_received": 0
    }

    for event in events:
        if event.player_id == match.player1_id:
            if event.event_type in ["1pt", "2pt", "3pt"]:
                player1_stats["points"] += int(event.event_type[0])
            elif event.event_type == "rebound":
                player1_stats["rebounds"] += 1
            elif event.event_type == "foul_given":
                player1_stats["fouls_committed"] += 1
                player2_stats["fouls_received"] += 1
        elif event.player_id == match.player2_id:
            if event.event_type in ["1pt", "2pt", "3pt"]:
                player2_stats["points"] += int(event.event_type[0])
            elif event.event_type == "rebound":
                player2_stats["rebounds"] += 1
            elif event.event_type == "foul_given":
                player2_stats["fouls_committed"] += 1
                player1_stats["fouls_received"] += 1

    # Update player stats
    player1 = db.query(User).filter(User.id == match.player1_id).first()
    player2 = db.query(User).filter(User.id == match.player2_id).first()

    if player1:
        player1.one_on_one_points_scored += match.player1_score
        player1.one_on_one_points_allowed += match.player2_score
        player1.total_points += player1_stats["points"]
        player1.total_rebounds += player1_stats["rebounds"]
        player1.total_fouls_committed += player1_stats["fouls_committed"]
        player1.total_fouls_received += player1_stats["fouls_received"]
        player1.total_games += 1
        if match.winner_id == match.player1_id:
            player1.one_on_one_wins += 1
            player1.total_wins += 1
        else:
            player1.one_on_one_losses += 1
            player1.total_losses += 1

    if player2:
        player2.one_on_one_points_scored += match.player2_score
        player2.one_on_one_points_allowed += match.player1_score
        player2.total_points += player2_stats["points"]
        player2.total_rebounds += player2_stats["rebounds"]
        player2.total_fouls_committed += player2_stats["fouls_committed"]
        player2.total_fouls_received += player2_stats["fouls_received"]
        player2.total_games += 1
        if match.winner_id == match.player2_id:
            player2.one_on_one_wins += 1
            player2.total_wins += 1
        else:
            player2.one_on_one_losses += 1
            player2.total_losses += 1

    db.commit()

    return RedirectResponse(url=f"/1v1/{match_id}", status_code=303)


# ============ Player Stats & Heat Map ============

@app.get("/player/{user_id}/heatmap", response_class=HTMLResponse)
async def player_heatmap(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    player = db.query(User).filter(User.id == user_id).first()
    if not player:
        return RedirectResponse(url="/", status_code=303)

    # Get all shot events from 1v1 matches
    one_on_one_shots = db.query(OneOnOneEvent).filter(
        OneOnOneEvent.player_id == user_id,
        OneOnOneEvent.event_type.in_(["1pt", "2pt", "3pt"]),
        OneOnOneEvent.shot_x.isnot(None),
        OneOnOneEvent.shot_y.isnot(None)
    ).all()

    # Get all shot events from team matches
    team_shots = db.query(MatchEvent).filter(
        MatchEvent.player_id == user_id,
        MatchEvent.event_type.in_(["1pt", "2pt", "3pt"]),
        MatchEvent.shot_x.isnot(None),
        MatchEvent.shot_y.isnot(None)
    ).all()

    # Combine all shots
    all_shots = []
    for shot in one_on_one_shots:
        all_shots.append({
            "x": shot.shot_x,
            "y": shot.shot_y,
            "type": shot.event_type
        })
    for shot in team_shots:
        all_shots.append({
            "x": shot.shot_x,
            "y": shot.shot_y,
            "type": shot.event_type
        })

    # Calculate shooting zones
    one_pointers = [s for s in all_shots if s["type"] == "1pt"]
    two_pointers = [s for s in all_shots if s["type"] == "2pt"]
    three_pointers = [s for s in all_shots if s["type"] == "3pt"]

    # Calculate shooting percentage by zone
    zones = {
        "paint": {"attempts": 0, "made": 0},
        "midrange": {"attempts": 0, "made": 0},
        "three_point": {"attempts": 0, "made": 0}
    }

    for shot in all_shots:
        x, y = shot["x"], shot["y"]
        # Simple zone classification
        if y > 60:  # Paint area
            zones["paint"]["attempts"] += 1
        elif y > 30:  # Midrange
            zones["midrange"]["attempts"] += 1
        else:  # Three point
            zones["three_point"]["attempts"] += 1

    return templates.TemplateResponse("player_heatmap.html", {
        "request": request,
        "user": current_user,
        "player": player,
        "one_pointers": one_pointers,
        "two_pointers": two_pointers,
        "three_pointers": three_pointers,
        "zones": zones
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
