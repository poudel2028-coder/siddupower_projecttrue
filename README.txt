Sports Stats Tracking App
==========================

A social sports stat tracking web app for friends, focused on basketball.
Features include user accounts, team management, friend system, challenges,
live referee dashboard, and permanent stat tracking.

Tech Stack
----------
- Backend: FastAPI (Python)
- Database: SQLite (SQLAlchemy)
- Frontend: HTML, CSS, Vanilla JS (Jinja2 templates)
- Real-time: JavaScript polling for live scoreboard updates
- Design: Dark mode, minimal, Apple-inspired aesthetic

Local Setup
-----------

1. Install Python 3.8 or higher if not already installed

2. Navigate to the project directory:
   cd /path/to/siddu_power_projectrs

3. Create a virtual environment:
   python -m venv venv

4. Activate the virtual environment:
   On macOS/Linux:
     source venv/bin/activate
   On Windows:
     venv\Scripts\activate

5. Install dependencies:
   pip install -r requirements.txt

6. Run the application:
   python main.py

7. Open your browser and visit:
   http://localhost:8000

Note: For production deployment, change the secret key in main.py
(line 17) from "your-secret-key-change-this-in-production" to a
secure random string. You can generate one with:
python -c "import secrets; print(secrets.token_urlsafe(32))"

The app will create a SQLite database file (sports_stats.db) automatically
on first run.

Deployment to Multiple Devices
==============================

Option 1: PythonAnywhere (Free, Recommended)
--------------------------------------------

PythonAnywhere offers a free tier that's perfect for this app.

Steps:

1. Create an account at https://www.pythonanywhere.com

2. Go to the "Web" tab and click "Add a new web app"

3. Choose "Flask" (we'll configure it for FastAPI)
   - Python version: 3.8 or higher
   - Web app name: sports-stats (or your choice)

4. Open a Bash console:
   - Go to the "Consoles" tab
   - Click "Bash"
   - Clone or upload your project files

5. In the Bash console, navigate to your project:
   cd sports-stats

6. Create a virtual environment:
   python3 -m venv venv
   source venv/bin/activate

7. Install dependencies:
   pip install -r requirements.txt

8. Modify the WSGI configuration:
   - Go back to the "Web" tab
   - Click on the "WSGI configuration file" link
   - Replace the contents with:

   import sys
   path = '/home/yourusername/sports-stats'
   if path not in sys.path:
       sys.path.append(path)
   
   from main import app
   application = app

9. IMPORTANT: Set a secure secret key:
   - In main.py, line 17, change "your-secret-key-change-this-in-production"
   - Generate a secure key: python -c "import secrets; print(secrets.token_urlsafe(32))"
   - Replace the placeholder with your generated key

10. Update the web app configuration:
   - In the "Web" tab, under "Code":
   - Working directory: /home/yourusername/sports-stats
   - Virtualenv: /home/yourusername/sports-stats/venv

10. Add a static files mapping:
    - URL directory: /static/
    - Directory path: /home/yourusername/sports-stats/static

11. Reload the web app:
    - Click the green "Reload" button in the Web tab

12. Your app will be available at:
    https://yourusername.pythonanywhere.com

13. Share this URL with your friends so they can access it from any device.

Important Notes for PythonAnywhere:
- The free tier has some limitations (no background tasks, limited CPU)
- SQLite works fine on PythonAnywhere
- Session data is stored in memory (sessions will reset on reload)
- For production, consider adding a proper session backend


Option 2: Railway (Free, Modern)
---------------------------------

Railway offers a modern deployment experience with a free tier.

Steps:

1. Create an account at https://railway.app

2. Install the Railway CLI (optional, or use the web interface):
   npm install -g @railway/cli

3. Initialize your project:
   railway login
   railway init

4. Deploy using the web interface:
   - Go to https://railway.app/new
   - Select "Deploy from GitHub repo" (if your code is on GitHub)
   - Or select "Empty Project" and upload files

5. Configure the project:
   - Add a new service: select "Python"
   - Railway will detect requirements.txt automatically
   - Set the start command: uvicorn main:app --host 0.0.0.0 --port $PORT

6. Add environment variables:
   - SECRET_KEY: Generate a secure key and add it here
   - Update main.py to use: secret_key=os.environ.get("SECRET_KEY", "fallback-key")

7. Deploy:
   - Railway provides a PORT variable automatically

7. Deploy:
   - Railway will build and deploy automatically
   - You'll get a public URL like: https://your-app.railway.app

8. Share the URL with your friends.

Important Notes for Railway:
- The free tier includes $5 credit/month
- After credits expire, you may need to pay or move to another platform
- Railway provides a persistent database option (PostgreSQL) if needed


Option 3: Render (Free Tier Available)
---------------------------------------

Render is another great option with a free tier for web services.

Steps:

1. Create an account at https://render.com

2. Push your code to GitHub (required for Render)

3. Create a new Web Service:
   - Connect your GitHub repository
   - Select the repository
   - Configure build settings:
     * Runtime: Python
     * Build Command: pip install -r requirements.txt
     * Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT

4. Render will deploy automatically
5. You'll get a URL like: https://your-app.onrender.com

6. Share the URL with your friends.

Important Notes for Render:
- Free web services spin down after 15 minutes of inactivity
- Cold starts can take 30-60 seconds
- Database is available as a separate service (PostgreSQL)
- SQLite works fine for the free tier


Option 4: Ngrok (For Quick Testing)
------------------------------------

If you want to quickly share your local running app with friends:

1. Install ngrok: https://ngrok.com/download

2. Run your local app:
   python main.py

3. In a new terminal, run:
   ngrok http 8000

4. Ngrok will give you a public URL like:
   https://random-string.ngrok.io

5. Share this URL with your friends.

Important Notes for Ngrok:
- Free tier URLs change every time you restart ngrok
- Only works while your computer is running
- Great for testing, not for permanent deployment
- Requires your computer to be online


Recommendation
--------------

For a permanent, free solution that multiple friends can access anytime:
- Use PythonAnywhere (most stable free tier)
- Or use Render (modern interface, but with cold starts)

For quick testing with friends:
- Use Ngrok to share your local app


Troubleshooting
---------------

1. Database permissions error:
   - Ensure the directory is writable
   - On PythonAnywhere, the database will be created in your home directory

2. Import errors:
   - Make sure all dependencies are installed
   - Check that you're in the correct directory

3. Session issues:
   - Sessions are stored in memory by default
   - For production, consider using Redis or a database-backed session

4. Static files not loading:
   - Check that static files are properly configured
   - Verify the static files mapping in your deployment platform


File Structure
--------------

main.py                  - FastAPI application with all routes
models.py                - SQLAlchemy database models
database.py              - Database connection setup
requirements.txt         - Python dependencies
README.txt              - This file
PROJECT_STRUCTURE.txt   - Detailed file structure
static/
  css/
    style.css           - Global dark mode styles
  js/
    referee.js           - Referee dashboard JavaScript
templates/
  base.html             - Base template with dark theme
  login.html            - Login page
  register.html         - Registration page
  dashboard.html        - User dashboard with stats
  friends.html          - Friends management
  friend_profile.html   - Friend profile view
  teams.html            - Team management
  team_detail.html      - Team page with roster
  challenge.html        - Challenge another team
  match_detail.html     - Match details
  referee.html          - Referee dashboard
  scoreboard.html       - Live scoreboard view


Features
--------

- User authentication (login/register)
- Personal stats dashboard (points, wins, losses, free throws, fouls)
- Friend system with profile viewing
- Team creation with unique join codes
- Team joining via codes
- Team captain system
- Match challenges between teams
- Referee nomination system
- Live referee dashboard with large tap targets
- Real-time scoreboard updates (polling)
- Match event logging (2pt, 3pt, FT, fouls)
- Automatic MVP calculation
- Permanent stat recording after matches
- Mobile-optimized design
- Dark mode, minimal aesthetic


Design Philosophy
----------------

The app follows Apple's design principles:
- Minimal interface with clean typography
- Dark mode with subtle grays
- Large touch targets for mobile use
- Smooth transitions and interactions
- Focus on content over decoration


Support
-------

For issues or questions, check the code comments or review the
implementation in main.py and the templates.
