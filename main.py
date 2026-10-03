from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from database import init_db, get_db
from models import User, Friendship, Team, TeamMember, Match, MatchEvent
from datetime import datetime
import random
import string

app = FastAPI()

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


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "recent_matches": recent_matches,
        "user_teams": user_teams
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
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already exists"
        })
    
    user = User(
        username=username,
        password_hash=get_password_hash(password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/friends", response_class=HTMLResponse)
async def friends_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    friends = []
    for friendship in current_user.friendships_sent:
        friend = db.query(User).filter(User.id == friendship.friend_id).first()
        if friend:
            friends.append(friend)
    
    for friendship in current_user.friendships_received:
        friend = db.query(User).filter(User.id == friendship.user_id).first()
        if friend:
            friends.append(friend)

    return templates.TemplateResponse("friends.html", {
        "request": request,
        "user": current_user,
        "friends": friends
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
        return RedirectResponse(url="/friends?error=Already friends", status_code=303)

    friendship = Friendship(user_id=current_user.id, friend_id=friend.id)
    db.add(friendship)
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
    return templates.TemplateResponse("friend_profile.html", {
        "request": request,
        "user": current_user,
        "friend": friend
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
        captain_id=current_user.id
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

    # Get friends for referee selection
    friends = []
    for friendship in current_user.friendships_sent:
        friend = db.query(User).filter(User.id == friendship.friend_id).first()
        if friend:
            friends.append(friend)
    
    for friendship in current_user.friendships_received:
        friend = db.query(User).filter(User.id == friendship.user_id).first()
        if friend:
            friends.append(friend)

    return templates.TemplateResponse("challenge.html", {
        "request": request,
        "user": current_user,
        "user_teams": user_teams,
        "all_teams": all_teams,
        "friends": friends
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

    match = Match(
        team1_id=team1_id,
        team2_id=team2_id,
        referee_id=referee_id,
        status="pending"
    )
    db.add(match)
    db.commit()
    db.refresh(match)

    return RedirectResponse(url=f"/match/{match.id}", status_code=303)


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

    return templates.TemplateResponse("match_detail.html", {
        "request": request,
        "user": current_user,
        "match": match,
        "team1": team1,
        "team2": team2,
        "referee": referee,
        "team1_members": team1_members,
        "team2_members": team2_members
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
        return RedirectResponse(url=f"/match/{match_id}?error=Not authorized", status_code=303)

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

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match or match.referee_id != current_user.id:
        return RedirectResponse(url="/", status_code=303)

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


@app.post("/referee/event")
async def record_event(
    request: Request,
    match_id: int = Form(...),
    player_id: int = Form(...),
    event_type: str = Form(...),
    target_player_id: int = Form(None),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return {"error": "Not authenticated"}

    match = db.query(Match).filter(Match.id == match_id).first()
    if not match or match.referee_id != current_user.id:
        return {"error": "Not authorized"}

    event = MatchEvent(
        match_id=match_id,
        player_id=player_id,
        event_type=event_type,
        target_player_id=target_player_id
    )
    db.add(event)

    # Update match score
    if event_type in ["2pt", "3pt", "ft"]:
        player = db.query(User).filter(User.id == player_id).first()
        # Determine which team the player is on
        team_membership = db.query(TeamMember).filter(
            TeamMember.user_id == player_id
        ).first()
        
        if team_membership:
            if team_membership.team_id == match.team1_id:
                match.team1_score += int(event_type[0])
            elif team_membership.team_id == match.team2_id:
                match.team2_score += int(event_type[0])

    db.commit()

    return {
        "success": True,
        "team1_score": match.team1_score,
        "team2_score": match.team2_score
    }


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

    # Calculate player stats and update profiles
    player_stats = {}
    for event in events:
        if event.player_id not in player_stats:
            player_stats[event.player_id] = {
                "points": 0,
                "fts": 0,
                "fouls_given": 0,
                "fouls_received": 0
            }
        
        if event.event_type == "2pt":
            player_stats[event.player_id]["points"] += 2
        elif event.event_type == "3pt":
            player_stats[event.player_id]["points"] += 3
        elif event.event_type == "ft":
            player_stats[event.player_id]["points"] += 1
            player_stats[event.player_id]["fts"] += 1
        elif event.event_type == "foul_given":
            player_stats[event.player_id]["fouls_given"] += 1
            if event.target_player_id:
                if event.target_player_id not in player_stats:
                    player_stats[event.target_player_id] = {
                        "points": 0,
                        "fts": 0,
                        "fouls_given": 0,
                        "fouls_received": 0
                    }
                player_stats[event.target_player_id]["fouls_received"] += 1

    # Find MVP (player with most points)
    mvp_id = None
    max_points = 0
    for player_id, stats in player_stats.items():
        if stats["points"] > max_points:
            max_points = stats["points"]
            mvp_id = player_id

    match.mvp_id = mvp_id

    # Update user profiles
    for player_id, stats in player_stats.items():
        user = db.query(User).filter(User.id == player_id).first()
        if user:
            user.total_points += stats["points"]
            user.total_free_throws += stats["fts"]
            user.total_fouls_committed += stats["fouls_given"]
            user.total_fouls_received += stats["fouls_received"]
            user.total_games += 1

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
