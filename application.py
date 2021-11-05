'''
TOOL SHARE

steven small
stvnsmll

Full Project Structure:
~/toolshare
    |-- application.py              # main script (this file)
    |__ /views                      # contains all blueprints for app.routes
         |-- __init__.py            #   empty
         |-- neighborhoods.py
         |-- tools_and_actions.py
         |-- users.py
    |__ /sub_modules                # contains all helper and supporting functions
         |-- __init__.py            #   imports all from each sub module
         |-- helpers.py
         |-- config.py
         |-- emails.py
         |-- image_mgmt.py
         |-- SQL.py
    |__ /templates                  # contains all of the html jinja layout templates and files
         |-- layout.html
         |__ /accountmgmt
         |__ /emailtemplates
         |__ /FAQs                  #   sub-folder with its own layout template and files for FAQs
              |-- FAQ_home.html
              |-- FAQ_layout.html
              |__ /pages
         |__ /general
         |__ /neighborhood
         |__ /tools
    |__ /static
         |__ /LandingMedia
         |__ /manifest
         |__ /toolimages
         |-- FOO.js
         |-- BAR.css
         |-- other_images.png
         ...
    |-- requirements.txt
    |-- toolshare.db
    |-- README.md
    |-- LICENSE
    |-- Procfile


application.py (main) Structure:
    1- Library imports
    2- Flask application setup
        A- Initialize the Flask app
        B- Configure the database
        C- Setup AWS S3 for image storage
        D- Configure email functionality
        E- Webapp installation requirements
    3 - Register Bluebprints (app routes)
        A- Main features: tools & actions
        B- Neighborhood management
        C- User management
    4- Misc other helper functions

'''






################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [1]   IMPORTS                                         | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

import os
import boto3, botocore

from flask import Flask, send_from_directory, make_response
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError


#for sending emails
from flask_mail import Mail

#import all of the helper functions from sub_modules (helpers.py, emails.py, image_mgmt.py, SQL.py)
from sub_modules import *
from sub_modules import config

#import blueprints for all of the app.routes
from views.neighborhoods import neighborhoods_bp
from views.tools_and_actions import tools_and_actions_bp
from views.users import users_bp






################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [2]   FLASK APPLICATION SETUP                         | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################


#----------------------------------------------------
# A- INITIALIZE FLASK APP

# Configure application
app = Flask(__name__)


# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response



#----------------------------------------------------
# B- CONFIGURE DATABASE

# sqlite = 1 (development)
# postgreSQL = 2 (production on Heroku)
DATABASE__TYPE = 2
try:
    db = SQL.SQL_db(os.getenv("DATABASE_URL"))
    print("postgreSQL database: production mode")
except:
    print("UNABLE TO CONNECT TO postgreSQL DATABASE")
    db = SQL.SQL_db("sqlite:///toolshare.db")
    app.config["SESSION_FILE_DIR"] = mkdtemp()# <-- not used for Heroku
    print("sqlite3 database: development mode")
    DATABASE__TYPE = 1
# assign the database object to a config variable to be accessed by other modules
app.config['database_object'] = db


Session(app)



#----------------------------------------------------
# C- SETUP STORAGE ON S3 FOR IMAGES

# setup s3 file storage
app.config['S3_BUCKET'] = config.S3_BUCKET
app.config['S3_REGION'] = config.S3_REGION
app.config['S3_KEY'] = os.environ.get('AWS_ACCESS_KEY_ID')
app.config['S3_SECRET'] = os.environ.get('AWS_SECRET_ACCESS_KEY')

app.config['S3_LOCATION'] = 'http://{}.s3.amazonaws.com/'.format(config.S3_BUCKET)

s3 = boto3.client(
   "s3",
   aws_access_key_id=app.config['S3_KEY'],
   aws_secret_access_key=app.config['S3_SECRET'],
   region_name=app.config['S3_REGION'],
   config=botocore.client.Config(signature_version='s3v4')
)
# assign the s3 object to a config variable to be accessed by other modules
app.config["s3_object"] = s3

# Used for *local* image upload
# code credit: https://roytuts.com/upload-and-display-image-using-python-flask/
UPLOAD_FOLDER = 'static/toolimages/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024



#----------------------------------------------------
# D- CONFIGURE EMAIL FUNCTIONALITY

app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)
# set to 1 to send emails when every action happens (approve or reject)
# set to 0 to only send the required account management emails
SEND_EMAIL_ACTIONS = 0
app.config["SEND_EMAIL_ACTIONS"] = SEND_EMAIL_ACTIONS
app.config["mail_object"] = mail



#----------------------------------------------------
# E- WEB APP INSTALLATION REQUIREMENTS

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static/manifest', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    response = make_response(send_from_directory('static', 'sw.js'))
    response.headers['Cache-Control'] = 'no-cache'
    return response






################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [3]   REGISTER BLUEPRINTS (routes)                    | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################


#----------------------------------------------------
# A- MAIN FEATURES: TOOLS & ACTIONS 
app.register_blueprint(tools_and_actions_bp)


#----------------------------------------------------
# B- NEIGHBORHOOD MANAGEMENT
app.register_blueprint(neighborhoods_bp)


#----------------------------------------------------
# C- USER MANAGEMENT
app.register_blueprint(users_bp)






################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [4]   misc other helper functions...                  | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)

# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
