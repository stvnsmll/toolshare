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

#for baggage
import io
import base64
import sub_modules
import datetime
import requests
#for baggage

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


#tmp. for the lugger tracker
@app.route("/found_luggage", methods=["GET", "POST"])
def found_luggage():
    '''Log user out'''
    if request.method == "POST":
        #confirm reCaptcha
        if DATABASE__TYPE == 1:#no captcha needed
            recaptcha_passed = True
        else:
            print("POST from the production bag website")
            parameters = request.form
            print(parameters)
            recaptcha_passed = False
            print("testing recaptcha")
            recaptcha_response = parameters.get('g-recaptcha-response')
            try:
                recaptcha_secret = os.environ.get('RECAPTCHA_SECRET')
                response = requests.post(f'https://www.google.com/recaptcha/api/siteverify?secret={recaptcha_secret}&response={recaptcha_response}').json()
                recaptcha_passed = response.get('success')
            except Exception as e:
                print(f"failed to get reCaptcha: {e}")
                return apology("reCaptcha fail...")
            print(f"reCaptcha Status: {recaptcha_passed}")
        if recaptcha_passed:
            returnAction = request.form.get("returnAction")
            longitude = request.form.get("longit")
            latitude = request.form.get("latit")
            bag_name = request.form.get("bag_name")
            bagID = request.form.get("bagID")
            ipaddress = request.form.get("ipaddress")
            usermessage = request.form.get("usermessage")
            print(f"The included message was: {usermessage}")
            print(f"IP Address: {ipaddress}")
            email_address = os.environ.get('BAG_EMAIL')
            print(returnAction)
            noEmail = request.form.get("noEmail")
            location_shared = 0
            if returnAction == "location":
                maplink = "https://www.latlong.net/c/?lat=" + latitude + "&long=" + longitude
                print(f"Bag location = Lo:{longitude}, La:{latitude}")
                print(maplink)
                location_shared = 1
                #send email
                print("send the location email!")
                now = datetime.datetime.now()
                message = f"Bag: {bag_name} scanned at {now}\n\nIP Addr: {ipaddress}\n\nLatLong={latitude}:{longitude}\n{maplink}\n\nMessage:\n{usermessage}"
                if noEmail != "1":#don't send if in development mode...
                    sub_modules.emails.send_mail([email_address],"bag log - LOCATION!",message)
                    #pass
                print("location mail sent")
            if returnAction == "sendMessage":
                print("send the message email!")
                now = datetime.datetime.now()
                message = f"Bag: {bag_name} scanned at {now}\n\nIP Addr: {ipaddress}\n\nMessage:\n{usermessage}"
                sub_modules.emails.send_mail([email_address],"bag log - message!",message)
                print(".mail sent.")
            extra_url = ""
            extra_url2 = ""
            print(noEmail)
            if noEmail == "1":
                extra_url = "&noEmail=1"
            if location_shared == 1:
                extra_url2 = "&locshared=1"
            print(extra_url2)
            #if DATABASE__TYPE == 1:
            return redirect(url_for('found_luggage') + f'?bagID={bagID}' + extra_url + extra_url2)
            #else:
            #    fullURL = f"https://sharetools.tk/found_luggage?bagID={bagID}{extra_url}{extra_url2}"
            #    print(fullURL)
            #    return redirect(fullURL)
        else:#reCaptcha failed...
            return apology("reCaptcha fail...")

    else:#GET

        list_of_actual_bags = {
            "10d8520f7f2246c4b246437d6e5985e7": "green_carryon",
            "6851b0e7efd640b3853ea2eda21c9863": "sjs_black_checkunder",
            "093bd25584754feab29938fcbd85193e": "hcs_grey_checkunder",
            "0198f1b8385a4c61b116b80cb7f3eca1": "big_carryon_backpack",
            "6ce2b15894c4414f88627f9cf673d273": "small_roller_carryon_black",
            "8e7d5a80643843d6bc84c8eb73678d1c": "green_duffel_bag",
            "25a98613f623400aa14336a47a5bae20": "sjs_volleyball_6_bag",
            "80aaa20845dc403cbe17704e8c1e5776": "purple_big_checkunder"
        }

        bagID = request.args.get("bagID")
        if bagID in list_of_actual_bags:
            print("valid bag")
        else:
            return render_template("foundluggage.html")
        bag_name = list_of_actual_bags[bagID]

        s3 = app.config["s3_object"]
        image_uuid_with_ext = bagID + ".jpeg"
        expire_in=3600
        imageURL = ""
        #get the bag image
        # just send the full asw filepath for now
        #return "{}{}".format(app.config["S3_LOCATION"], image_uuid_with_ext)  <--- delete this...
        # returns the presigned url for the full-sized image
        try:
            imageURL = s3.generate_presigned_url('get_object',
                                                        Params={'Bucket': app.config["S3_BUCKET"],
                                                                'Key': image_uuid_with_ext},
                                                        ExpiresIn=expire_in)#seconds
        except:# ClientError as e:
            #logging.error(e)
            e = "get_image_s3, misc error"
            print("Something Happened - ImageFetchFail: ", e)

        #personal details stored in environment variables
        luggage_owner = os.environ.get('BAG_OWNER')
        luggage_firstname = luggage_owner.split(" ")[0]
        email_address = os.environ.get('BAG_EMAIL')
        phone_number = os.environ.get('BAG_PHONE')
        address = os.environ.get('BAG_ADDRESS')
        if request.headers.getlist("X-Forwarded-For"):
            print(request.headers.getlist("X-Forwarded-For"))
            visiting_IP = request.headers.getlist("X-Forwarded-For")[0]
        else:
            visiting_IP = request.remote_addr
        

        #send the email!
        noEmail = request.args.get("noEmail")
        if noEmail == "1":
            print("Don't send the email")
        else:
            noEmail = "0"
            print("send the email!")
            now = datetime.datetime.now()
            message = f"Bag: {bag_name} scanned at {now}\n\nIP Addr: {visiting_IP}"
            sub_modules.emails.send_mail([email_address],"bag log - scan",message)
            print(".mail sent.")
        #user selected to share their location
        locshared = request.args.get("locshared")
        if locshared == "1":
            #thank the user
            locshared = True
            pass
        else:
            locshared = False
    
        return render_template("foundluggage.html", owner=luggage_owner, 
                                                    firstname=luggage_firstname, 
                                                    email=email_address, 
                                                    phone=phone_number, 
                                                    address=address, 
                                                    bagID=bagID,
                                                    bag_name=bag_name,
                                                    ipaddress = visiting_IP,
                                                    imageURL = imageURL,
                                                    noEmail = noEmail,
                                                    locshared = locshared)

#tmp. for the lugger tracker
@app.route("/make_QR", methods=["GET", "POST"])
def make_QR_Code():
    if request.method == "POST":
        return apology("No POST allowed", 403)
    else:#GET
        bagID = request.args.get("bagID")
        noEmail = request.args.get("noEmail")
        extra_url = ""
        if noEmail == "1":
                extra_url = "&noEmail=1"
        img = qrcode.make(f"https://www.sharetools.tk/found_luggage?bagID={bagID}{extra_url}")
        data = io.BytesIO()
        img.save(data, "PNG")
        encoded_qr_image = base64.b64encode(data.getvalue())

        #pass to template:
        qrcode_data=encoded_qr_image.decode('utf-8')

        return render_template("simpleqrcode_page.html", qrcode_data = qrcode_data)



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
