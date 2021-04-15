'''
TOOL SHARE

steven small
stvnsmll


application.py section layout:

1- Library imports
2- Flask application setup

3- Main features: tools & actions
4- Neighborhood management
5- User management
6- Misc other helper functions

'''




################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [1]   LIBRARY IMPORTS                                 | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

import os
import datetime
import uuid

#from cs50 import SQL
import SQL
import config
import boto3, botocore
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, send_from_directory, make_response
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
# importing Image class from PIL package for creating tool image thumbnails
from PIL import Image
#for sending emails
from flask_mail import Mail, Message

from helpers import apology, login_required, neighborhood_required



################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [2]   FLASK APPLICATION SETUP                         | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

# Configure application
app = Flask(__name__)

# API KEY: (delete when finished with the app)
# export API_KEY=pk_1f1a8259d76a44099ff0084bf01c1d97

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# sqlite = 1 (development)
# postgreSQL = 2 (production on Heroku)
DATABASE__TYPE = 2
try:
    db = SQL.SQL_db(os.getenv("DATABASE_URL"))
except:
    db = SQL.SQL_db("sqlite:///toolshare.db")
    app.config["SESSION_FILE_DIR"] = mkdtemp()# <-- not used for Heroku
    print("sqlite3 database: development mode")
    DATABASE__TYPE = 1

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

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

# Used for *local* image upload
# code credit: https://roytuts.com/upload-and-display-image-using-python-flask/
UPLOAD_FOLDER = 'static/toolimages/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Setup pconfiguration for email:
mail = Mail(app)
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)

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
# |    [3]   MAIN FEATURES: TOOLS & ACTIONS                  | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

@app.route("/")
@login_required
def index():
    """Show tool management page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    # get all user tools
    mytoollist = db.execute("SELECT * FROM tools WHERE owneruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL
    mytools = format_tools(mytoollist)

    #check if the user is part of a neighborhood
    if session.get("neighborhood_check") == "0":
        borrowedtools = ['no-nbh']
    else:
        # get all of the tools that the user has borrowed
        borrowedlist = db.execute("SELECT * FROM tools WHERE activeuseruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL
        borrowedtools = format_tools(borrowedlist)
    # render the template
    return render_template("index.html", setActive1="active", openActions=countActions(), firstname=firstname, mytools=mytools, borrowedtools=borrowedtools)


@app.route('/myTools')
@login_required
def my_redirect1():
    return redirect(url_for('index') + '#myTools')


@app.route('/borrowed')
@login_required
def my_redirect2():
    return redirect(url_for('index') + '#borrowed')


@app.route("/actions", methods=["GET", "POST"])
@login_required
def actions():
    """Show user actions page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        myOpenApprovals = db.execute("SELECT * FROM actions WHERE targetuuid = :userUUID AND state = 'open' AND type = 'toolrequest' AND deleted = 0;", userUUID=userUUID)
        myapprovals = {}
        for item in myOpenApprovals:
            requestordeetz = db.execute("SELECT * FROM users WHERE uuid = :requestoruuid;", requestoruuid=item['originuuid'])[0]
            tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid;", toolid=item["toolid"])[0]
            toolowner = db.execute("SELECT * FROM users WHERE uuid = :toolowner;", toolowner=tooldetails['owneruuid'])[0]
            d = datetime.datetime.strptime(item["timestamp_open"], '%Y-%m-%d %H:%M:%S')
            requestDate = d.strftime('%b %d, %Y')
            if tooldetails["photo"] == "none":
                photo = ""
            else:
                photo = get_image_s3(item["toolid"] + ".jpeg")
            commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B);", A=userUUID, B=item['originuuid'])
            commonneighborhoods = []
            for i in commonneighborhoods_data:
                commonneighborhoods.append(i['neighborhood'])
            info = {'toolname': tooldetails["toolname"],
                    'toolid': tooldetails["toolid"],
                    'requestorusername': requestordeetz['username'],
                    'requestorfirstname': requestordeetz['firstname'],
                    'commonNeighborhoods': commonneighborhoods,
                    'requestDate': requestDate,
                    'state': item["state"],
                    'messages': item["messages"].split("\n"),
                    'actionid': item["actionid"],
                    'photo': photo}
            myapprovals[item["actionid"]] = info

        myOpenRequests = db.execute("SELECT * FROM actions WHERE originuuid = :userUUID AND state NOT LIKE 'dismissed' AND deleted = 0;", userUUID=userUUID)
        myrequests = {}
        for item in myOpenRequests[::-1]:
            tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid;", toolid=item["toolid"])[0]
            toolowner = db.execute("SELECT * FROM users WHERE uuid = :toolowner;", toolowner=tooldetails['owneruuid'])[0]
            d = datetime.datetime.strptime(item["timestamp_open"], '%Y-%m-%d %H:%M:%S')
            requestDate = d.strftime('%b %d, %Y')
            if tooldetails["photo"] == "none":
                photo = ""
            else:
                photo = get_image_s3(item["toolid"] + ".jpeg")
            commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B);", A=userUUID, B=tooldetails['owneruuid'])
            commonneighborhoods = []
            for i in commonneighborhoods_data:
                commonneighborhoods.append(i['neighborhood'])
            info = {'toolname': tooldetails["toolname"],
                    'toolid': tooldetails["toolid"],
                    'ownerusername': toolowner["username"],
                    'ownerfirstname': toolowner["firstname"],
                    'commonNeighborhoods': commonneighborhoods,
                    'requestorfirstname': firstname,
                    'requestDate': requestDate,
                    'state': item["state"],
                    'messages': item["messages"].split("\n"),
                    'actionid': item["actionid"],
                    'photo': photo}
            myrequests[item["actionid"]] = info
        return render_template("actions.html", setActive2="active", openActions=countActions(), firstname=firstname, myrequests=myrequests, myapprovals=myapprovals)
    else:
        returnedAction = request.form.get("returnedAction")
        if returnedAction == 'fromMyRequests':
            returnedActionID = request.form.get("returnedActionID")
            dismissOrCancel = request.form.get("dismissOrCancel")
            # console log display
            print(returnedAction + ", actionid: " + returnedActionID + " -- " + dismissOrCancel)
            # database update to either cancel or dismiss
            if dismissOrCancel == "dismiss":
                db.execute("UPDATE actions SET state = 'dismissed' WHERE actionid = :returnedActionID;", returnedActionID=returnedActionID)
            else: # cancel, to cancel a request that the active user originated
                # cancel whatever the tool had as the open action
                toolid = db.execute("SELECT toolid FROM actions WHERE actionid = :returnedActionID;", returnedActionID=returnedActionID)[0]['toolid']
                tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid;", toolid=toolid)[0]
                if tooldetails['state'] == 'requested':
                    db.execute("UPDATE tools SET state = 'available', activeuseruuid = NULL WHERE toolid = :toolid;", toolid=toolid)
                else: # I think the only other possible state is 'overdue'
                    db.execute("UPDATE tools SET state = 'borrowed' WHERE toolid = :toolid;", toolid=toolid)
                # set the action in the actions table to dismissed (and close the timestamp)
                db.execute("UPDATE actions SET state = 'dismissed', timestamp_close = :closetime WHERE actionid = :returnedActionID;", closetime=datetime.datetime.now(), returnedActionID=returnedActionID)
                #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
                logHistory("tool", "cancel", tooldetails['owneruuid'], toolid, "", "")
        else: # returned action came from the "My Approvals" tab
            returnedActionID = request.form.get("returnedActionID")
            approveOrReject = request.form.get("approveOrReject")
            approveReject_comments = request.form.get("approveReject_comments")
            # console log display
            print(returnedAction + ", actionid: " + returnedActionID + " -- " + approveOrReject + "\n Response Comments: " + approveReject_comments)
            action_deetz = db.execute("SELECT * FROM actions WHERE actionid = :returnedActionID;", returnedActionID=returnedActionID)[0]
            toolid = action_deetz['toolid']
            prev_comments = action_deetz['messages']
            all_comments = firstname + ': "' + approveReject_comments + '"' + "\n" + prev_comments
            # database update to either approve or reject
            if approveOrReject == "approve":
                # change the state of the actionid to show it is closed with closed date - add any comments
                db.execute("UPDATE actions SET state = 'closed', timestamp_close = :timeclose, messages = :comments WHERE actionid = :returnedActionID;", timeclose=datetime.datetime.now(), comments=all_comments, returnedActionID=returnedActionID)
                # change the state of the tool to borrowed
                db.execute("UPDATE tools SET state = 'borrowed' WHERE toolid = :toolid;", toolid=toolid)
                #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
                logHistory("tool", "approve", "", toolid, "", approveReject_comments)
                borroweruuid = db.execute("SELECT originuuid FROM actions WHERE actionid = :returnedActionID;", returnedActionID=returnedActionID)[0]['originuuid']
                logHistory("tool", "borrow", borroweruuid, toolid, "", approveReject_comments)
            else: # the request was rejected
                # change the state of the actionid to show it is closed with closed date - add any comments
                db.execute("UPDATE actions SET state = 'closed', timestamp_close = :timeclose, messages = :comments WHERE actionid = :returnedActionID;", timeclose=datetime.datetime.now(), comments=all_comments, returnedActionID=returnedActionID)
                # change the state of the tool to available
                db.execute("UPDATE tools SET state = 'available', activeuseruuid = NULL WHERE toolid = :toolid;", toolid=toolid)
                #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
                borroweruuid = db.execute("SELECT originuuid FROM actions WHERE actionid = :returnedActionID;", returnedActionID=returnedActionID)[0]['originuuid']
                logHistory("tool", "reject", borroweruuid, toolid, "", approveReject_comments)
        return ('', 204)


@app.route("/findtool", methods=["GET", "POST"])
@login_required
@neighborhood_required
def findtool():
    """Find a tool from all users' neighborhoods"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        # get all of the tools the user could borrow from their neighborhoods
        #alltoollist = db.execute("SELECT * FROM tools WHERE owneruuid IN (SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID)) AND private = 0 AND deleted = 0  ORDER BY toolname COLLATE NOCASE;", userUUID=userUUID)
        alltoollist = db.execute("SELECT * FROM tools WHERE toolid IN (SELECT DISTINCT toolid FROM toolvisibility WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID)) ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL
        #SELECT DISTINCT toolid FROM toolvisibility WHERE neighborhoodid IN (10, 13);
        alltools = format_tools(alltoollist)

        # render the template
        return render_template("findtool.html", openActions=countActions(), firstname=firstname, alltools=alltools)
    else:
        # get data from the form
        flash("do nothing???")
        return redirect(url_for('index') + '#borrowed')


@app.route("/newtool", methods=["GET", "POST"])
@login_required
def newtool():
    """Create a new tool"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")

    myNeighborhoodsData = db.execute("SELECT neighborhoodid, neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID);", userUUID=userUUID)
    myNeighborhoods = {}
    for i in range(len(myNeighborhoodsData)):
        info = {'neighborhoodID': myNeighborhoodsData[i]['neighborhoodid'],
                'neighborhoodName': myNeighborhoodsData[i]['neighborhood']}
        myNeighborhoods[myNeighborhoodsData[i]['neighborhoodid']] = info

    if request.method == "GET":
        return render_template("newtool.html", openActions=countActions(), firstname=firstname, myNeighborhoods=myNeighborhoods)

    else: # Post
        # get data from the form
        toolname = request.form.get("toolname")
        if toolname == "":
            flash("Tool entry error: please provide a tool name.")
            return render_template("newtool.html", openActions=countActions(), firstname=firstname, myNeighborhoods=myNeighborhoods)

        #Create the tools new UUID
        new_tool_uuid = uuid.uuid4().hex

        category = request.form.get("category")
        health = request.form.get("health")
        features = request.form.get("features")
        notes = request.form.get("notes")

        toolvisibility = request.form.get("toolvis")
        #set tool relations to neighborhoods:
        if ((toolvisibility == 'private') or (toolvisibility == "")):
            private = 1
            # delete any relation from this tool to any of the users neighborhoods
            for nbh in myNeighborhoods:
                db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :new_tool_uuid;", nbh=nbh, new_tool_uuid=new_tool_uuid)
        elif toolvisibility == 'public':
            private = 0
            #create tool relationships to all the users neighborhoods
            for nbh in myNeighborhoods:
                exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :new_tool_uuid;", nbh=nbh, new_tool_uuid=new_tool_uuid)
                if len(exists) == 0:
                    db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", nbh, new_tool_uuid)
        else: #user selected custom
            private = 2
            # delete relations that are not checked
            # create tool relationships to the ones that are checked
            NBH_include_list = toolvisibility.split(',')
            #print(NBH_include_list)
            for nbh in myNeighborhoods:
                #print(nbh)
                #print()
                if nbh in NBH_include_list:
                    exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :new_tool_uuid;", nbh=nbh, new_tool_uuid=new_tool_uuid)
                    if len(exists) == 0:
                        db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", nbh, new_tool_uuid)
                else:
                    db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :new_tool_uuid;", nbh=nbh, new_tool_uuid=new_tool_uuid)

        toolimage = "none"

        # Populate the database with the tool, regardless of image or not
        db.execute("INSERT INTO tools (toolid, owneruuid, health, photo, features, category, toolname, notes, private) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", new_tool_uuid, userUUID, health, toolimage, features, category, toolname, notes, private)

        # check for image upload with the new tool
        for uploaded_file in request.files.getlist('imagefile'):
            if uploaded_file.filename != '':
                #print(uploaded_file.filename)
                #filename = secure_filename(uploaded_file.filename)
                #uploaded_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                filename = str(new_tool_uuid) + ".jpeg"
                uploaded_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                # create thumbnail
                save_local_thumbnail(new_tool_uuid)

                images_to_s3(new_tool_uuid)

                db.execute("UPDATE tools SET photo = :filename WHERE toolid = :new_tool_uuid;", filename=filename, new_tool_uuid=new_tool_uuid)
                # update the database if a tool image exists
                print("Image added to database")

            else:
                print("no tool image file found....")

        #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("tool", "createtool", "", new_tool_uuid, "", "")

        flash("Successfully added the tool")
        return redirect(url_for('index') + '#myTools')


@app.route("/tool_details", methods=["GET", "POST"])
@login_required
def tool_details():
    """Show user tool details page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        toolid = request.args.get("toolid")
        if not toolid:
            return apology("Need to provide a tool id")
        tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)
        if len(tooldetails) == 0:
            # no shared neighborhoods, cannot view this tool
            return apology("No tool")
        tooldetails = tooldetails[0]
        toolname = tooldetails["toolname"]
        state = tooldetails["state"]
        category = tooldetails["category"]
        description = tooldetails["features"].split('\n')
        health = tooldetails["health"]
        private = tooldetails["private"]
        activeuserfirstname = ""
        activeuserusername = ""
        ownerdetails = db.execute("SELECT * FROM users WHERE uuid = :toolowner;", toolowner=tooldetails["owneruuid"])[0]
        ownerfirstname = ownerdetails['firstname']
        ownerusername = ownerdetails['username']
        ownerUUID = ownerdetails['uuid']
        sharedneighborhoods = db.execute("SELECT neighborhoodid FROM memberships WHERE useruuid = :ownerUUID INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID", ownerUUID=ownerUUID, userUUID=userUUID)
        if len(sharedneighborhoods) == 0:
            # no shared neighborhoods, cannot view this tool
            return apology("UNAUTHORIZED")

        if userUUID == tooldetails["owneruuid"]:
            yesowner = True
            #get the owner's private notes
            if tooldetails["notes"] == None:
                notes = []
            else:
                notes = tooldetails["notes"].split('\n')
            commonneighborhoods = "  ^-- that's you!"

            toolhistoryDB = db.execute("SELECT * FROM history WHERE toolid = :toolid;", toolid=toolid)
            counter = 1
            toolhistory = {}
            for event in toolhistoryDB[::-1]:#itearate through in reverse order
                refnumber = counter
                d = datetime.datetime.strptime(event["timestamp"], '%Y-%m-%d %H:%M:%S')
                date = d.strftime('%b %d')
                timestamp = d.strftime('%H:%M:%S - %b %d, %Y (UTC)')
                action = event["action"]
                comment = event["comment"]
                firstuuid = event["useruuid"]
                firstuser = ""
                seconduuid = event["seconduuid"]
                seconduser = ""
                if firstuuid != "":
                    firstuser = db.execute("SELECT username FROM users WHERE uuid = :uuid;", uuid=firstuuid)[0]['username']
                if seconduuid != "":
                    seconduser = db.execute("SELECT username FROM users WHERE uuid = :uuid;", uuid=seconduuid)[0]['username']

                description2 = getDescriptionTool(action, firstuser, seconduser, comment)
                counter += 1
                info = {"refnumber": refnumber, "date": date, "timestamp": timestamp, "action": action, "toolid": toolid, "toolname": toolname, "comment": description2}
                toolhistory[refnumber] = info
        else:
            yesowner = False
            notes = []
            commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B);", A=userUUID, B=ownerUUID)
            commonneighborhoods = []
            for i in commonneighborhoods_data:
                commonneighborhoods.append(i['neighborhood'])
            toolhistory = {}

        isavailable = False
        isborrowed = False
        isrequested = False
        isoverdue = False
        if state == 'available':
            isavailable = True
        elif state == 'requested':
            isrequested = True
        elif state == 'borrowed':
            isborrowed = True
        else:# overdue
            isoverdue = True

        if state != 'available':
            activeuserfirstname = db.execute("SELECT firstname FROM users WHERE uuid = :activeuser;", activeuser=tooldetails["activeuseruuid"])[0]['firstname']
            activeuserusername = db.execute("SELECT username FROM users WHERE uuid = :activeuser;", activeuser=tooldetails["activeuseruuid"])[0]['username']
            activeuseruuid = db.execute("SELECT uuid FROM users WHERE uuid = :activeuser;", activeuser=tooldetails["activeuseruuid"])[0]['uuid']
            if activeuseruuid == ownerUUID:
                commonneighborhoods = "(hey, that's you!)"
            else:
                commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B);", A=activeuseruuid, B=ownerUUID)
                commonneighborhoods = []
                for i in commonneighborhoods_data:
                    commonneighborhoods.append(i['neighborhood'])

        if tooldetails["activeuseruuid"] == userUUID:
            userborrowed = True
        else:
            userborrowed = False

        photo = ""
        if tooldetails["photo"] != 'none':
            photo = get_image_s3(toolid + ".jpeg")

        return render_template("tooldetails.html",
                                openActions=countActions(),
                                firstname=firstname,
                                activeuserfirstname=activeuserfirstname,
                                activeuserusername=activeuserusername,
                                ownerfirstname=ownerfirstname,
                                ownerusername=ownerusername,
                                toolname=toolname,
                                description=description,
                                yesowner=yesowner,
                                state=state,
                                isavailable=isavailable,
                                isborrowed=isborrowed,
                                isrequested=isrequested,
                                isoverdue=isoverdue,
                                userborrowed=userborrowed,
                                category=category,
                                health=health,
                                photo=photo,
                                private=private,
                                commonneighborhoods=commonneighborhoods,
                                notes=notes,
                                toolid=toolid,
                                toolhistory=toolhistory)
    else:
        formAction = request.form.get("returnedAction")
        toolid = request.form.get("toolid")
        if formAction == "returnHome":
            return redirect(url_for('index') + '#myTools')
        elif formAction == "requestBorrow":
            requestComment_raw = request.form.get("requestComment")
            if requestComment_raw == "":
                requestComment = ""
            else:
                requestComment = firstname + ': "' + requestComment_raw + '"'
            toolownerUUID = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["owneruuid"]
            db.execute("INSERT INTO actions (type, originuuid, targetuuid, toolid, messages, timestamp_open) VALUES (?, ?, ?, ?, ?, ?);", "toolrequest", userUUID, toolownerUUID, toolid, requestComment, datetime.datetime.now())
            db.execute("UPDATE tools SET state = 'requested', activeuseruuid = :userUUID WHERE toolid = :toolid;", toolid=toolid, userUUID=userUUID)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "request", toolownerUUID, toolid, "", request.form.get("requestComment"))
            # notify the tool owner via email
            #send_email_toolaction(toolid, othername, actionmsg)
            #send_email_toolaction(toolid, firstname, "requested")
            flash('Tool Requested')
            return redirect(url_for('index') + '#borrowed')
        elif formAction == "markBorrowed":
            db.execute("INSERT INTO actions (type, state, originuuid, targetuuid, toolid, messages, timestamp_open, timestamp_close) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", "toolrequest", "dismissed", userUUID, userUUID, toolid, "self borrow", datetime.datetime.now(), datetime.datetime.now())
            db.execute("UPDATE tools SET state = 'borrowed', activeuseruuid = :userUUID WHERE toolid = :toolid;", toolid=toolid, userUUID=userUUID)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "borrow", "", toolid, "", "self-borrowed")
            flash('Tool marked as Borrowed')
            return redirect(url_for('index') + '#borrowed')
        elif formAction == "returnTool":
            toolownerUUID = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["owneruuid"]
            if userUUID == toolownerUUID:
                message = "self return"
                state = "dismissed"
            else:
                message = firstname + " returned the tool."
                state = "closed"
            db.execute("INSERT INTO actions (type, state, originuuid, targetuuid, toolid, messages, timestamp_open, timestamp_close) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", "toolrequest", state, userUUID, userUUID, toolid, message, datetime.datetime.now(), datetime.datetime.now())
            db.execute("UPDATE tools SET state = 'available', activeuseruuid = NUlL WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            if message == "self return":
                seconduuid = ""
            else:
                seconduuid = toolownerUUID
            logHistory("tool", "return", seconduuid, toolid, "", message)
            flash('Tool returned')
            return redirect(url_for('index') + '#borrowed')
        elif formAction == "cancelRequest":
            actionid = db.execute("SELECT actionid FROM actions WHERE toolid = :toolid AND state = 'open' AND originuuid = :userUUID;", toolid=toolid, userUUID=userUUID)[0]['actionid']
            db.execute("UPDATE actions SET state = 'dismissed', timestamp_close = :timeclose WHERE actionid = :actionid;", timeclose=datetime.datetime.now(), actionid=actionid)
            db.execute("UPDATE tools SET state = 'available', activeuseruuid = NUlL WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            toolownerUUID = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["owneruuid"]
            logHistory("tool", "cancel", toolownerUUID, toolid, "", "")
            flash('Cancelled the tool request')
            return redirect(url_for('index') + '#borrowed')
        elif formAction == "approveRequest":
            actiondetails = db.execute("SELECT * FROM actions WHERE toolid = :toolid AND type = 'toolrequest' AND state = 'open' AND targetuuid = :userUUID;", toolid=toolid, userUUID=userUUID)[0]
            actionid = actiondetails['actionid']
            requestor = actiondetails['originuuid']
            db.execute("UPDATE actions SET state = 'closed', timestamp_close = :timeclose WHERE actionid = :actionid;", timeclose=datetime.datetime.now(), actionid=actionid)
            db.execute("UPDATE tools SET state = 'borrowed', activeuseruuid = :requestor WHERE toolid = :toolid;", requestor=requestor, toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "approve", requestor, toolid, "", "")#comment??
            flash('Tool request approved')
            return redirect(url_for('tool_details') + '?toolid=' + toolid)
        elif formAction == "denyRequest":
            actiondetails = db.execute("SELECT * FROM actions WHERE toolid = :toolid AND type = 'toolrequest' AND state = 'open' AND targetuuid = :userUUID;", toolid=toolid, userUUID=userUUID)[0]
            actionid = actiondetails['actionid']
            requestor = actiondetails['originuuid']
            db.execute("UPDATE actions SET state = 'closed', timestamp_close = :timeclose WHERE actionid = :actionid;", timeclose=datetime.datetime.now(), actionid=actionid)
            db.execute("UPDATE tools SET state = 'available', activeuseruuid = NULL WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "reject", requestor, toolid, "", "")#comment??
            flash('Tool request denied')
            return redirect(url_for('tool_details') + '?toolid=' + toolid)
        elif formAction == "requireReturn":
            # get the useruuid for who has the tool "activeuseruuid" of the tool
            activeuseruuid = db.execute("SELECT activeuseruuid FROM tools WHERE toolid = :toolid;", toolid=toolid)[0]['activeuseruuid']
            # create new return tool action ("requirereturn")
            db.execute("INSERT INTO actions (type, originuuid, targetuuid, toolid, messages, timestamp_open) VALUES (?, ?, ?, ?, ?, ?);", "requirereturn", userUUID, activeuseruuid, toolid, "The tool owner has requested their tool back", datetime.datetime.now())
            # change state of the tool to 'overdue'
            db.execute("UPDATE tools SET state = 'overdue' WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "requirereturn", activeuseruuid, toolid, "", "")
            flash('Tool return requested')
            return redirect(url_for('tool_details') + '?toolid=' + toolid)
        elif formAction == "edit":
            return redirect(url_for('edittool') + '?toolid=' + toolid)
        elif formAction == "makePublic":
            db.execute("UPDATE tools SET private = '0' WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "edittool", "", toolid, "", "Tool marked public.")
            flash('Tool marked as public')
            return redirect(url_for('tool_details') + '?toolid=' + toolid)
        elif formAction == "makePrivate":
            db.execute("UPDATE tools SET private = '1' WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "edittool", "", toolid, "", "Tool marked private.")
            flash('Tool marked as private')
            return redirect(url_for('tool_details') + '?toolid=' + toolid)
        elif formAction == "deleteTool":
            db.execute("UPDATE tools SET deleted = '1', photo = 'none' WHERE toolid = :toolid;", toolid=toolid)
            db.execute("DELETE FROM toolvisibility WHERE toolid = :toolid;", toolid=toolid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "deletetool", "", toolid, "", "")
            flash('Tool deleted')
            return redirect(url_for('index') + '#myTools')
        else:
            return apology("Misc error")


@app.route("/edittool", methods=["GET", "POST"])
@login_required
def edittool():
    """Show user edit tool page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")

    if request.method == "GET":
        toolid = request.args.get("toolid")
        if not toolid:
            return apology("Need to provide a tool id")

        tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]

        if userUUID != tooldetails["owneruuid"]:
            return apology("You are not the tool owner!")

        toolname = tooldetails["toolname"]
        category = tooldetails["category"]
        description = tooldetails["features"]
        health = tooldetails["health"]
        publicCheck = (1 - tooldetails["private"]) # to get the opposite
        notes = tooldetails["notes"]
        if notes == None:
            notes = ""
        photo = ""
        if tooldetails["photo"] != "none":
            photo = get_image_s3(toolid + ".jpeg")


        myNeighborhoodsData = db.execute("SELECT neighborhoodid, neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID);", userUUID=userUUID)

        toolvisDB = db.execute("SELECT * FROM toolvisibility WHERE toolid = :toolid;", toolid=toolid)
        toolvislist = []
        for i in toolvisDB:
            toolvislist.append(i['neighborhoodid'])

        myNeighborhoods = {}
        for i in range(len(myNeighborhoodsData)):
            if myNeighborhoodsData[i]['neighborhoodid'] in toolvislist:
                visible = True
            else:
                visible = False
            info = {'neighborhoodID': myNeighborhoodsData[i]['neighborhoodid'],
                    'neighborhoodName': myNeighborhoodsData[i]['neighborhood'],
                    'isVisible': visible}
            myNeighborhoods[myNeighborhoodsData[i]['neighborhoodid']] = info

        if len(toolvislist) == 0:
            #print("Tool is private")
            toolVis = 'private'
        elif len(toolvislist) == len(myNeighborhoods):
            #print("Tooll is public")
            toolVis = 'public'
        else:
            #print("Tool is Custom")
            toolVis = 'custom'

        return render_template("edittool.html", openActions=countActions(), firstname=firstname, toolname=toolname, publicCheck=publicCheck, description=description, category=category, health=health, photo=photo, toolid=toolid, notes=notes, myNeighborhoods=myNeighborhoods, toolVis=toolVis)
    else:
        toolid = request.form.get("toolid")
        toolname = request.form.get("toolname")
        if toolname == "":
            flash("Tool entry error: please provide a tool name.\nNo changes made to the tool.")
            return redirect(url_for('tool_details') + '?toolid=' + toolid)
        category = request.form.get("category")
        health = request.form.get("health")
        features = request.form.get("features")
        notes = request.form.get("notes")

        myNeighborhoodsData = db.execute("SELECT neighborhoodid, neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID);", userUUID=userUUID)
        myNeighborhoods = {}
        for i in range(len(myNeighborhoodsData)):
            info = {'neighborhoodID': myNeighborhoodsData[i]['neighborhoodid'],
                    'neighborhoodName': myNeighborhoodsData[i]['neighborhood']}
            myNeighborhoods[myNeighborhoodsData[i]['neighborhoodid']] = info

        toolvisibility = request.form.get("toolvis")
        #set tool relations to neighborhoods:
        if ((toolvisibility == 'private') or (toolvisibility == "")):
            private = 1
            # delete any relation from this tool to any of the users neighborhoods
            for nbh in myNeighborhoods:
                db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :toolid;", nbh=nbh, toolid=toolid)
        elif toolvisibility == 'public':
            private = 0
            #create tool relationships to all the users neighborhoods
            for nbh in myNeighborhoods:
                exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :toolid;", nbh=nbh, toolid=toolid)
                if len(exists) == 0:
                    db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", nbh, toolid)
        else: #user selected custom
            private = 2
            # delete relations that are not checked
            # create tool relationships to the ones that are checked
            NBH_include_list = toolvisibility.split(',')
            #print(NBH_include_list)
            for nbh in myNeighborhoods:
                #print(nbh)
                #print()
                if nbh in NBH_include_list:
                    exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :toolid;", nbh=nbh, toolid=toolid)
                    if len(exists) == 0:
                        db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", nbh, toolid)
                else:
                    db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :nbh AND toolid = :toolid;", nbh=nbh, toolid=toolid)


        photostate = request.form.get("photostate")
        #photostate can be 'changed', 'unchanged', or 'removed'

        if photostate == "changed":
            db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, health, features, notes, toolid)
            # check for image upload with the updated tool data
            for uploaded_file in request.files.getlist('imagefile'):
                if uploaded_file.filename != '':
                    #print(uploaded_file.filename)
                    #filename = secure_filename(uploaded_file.filename)
                    #uploaded_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    filename = str(toolid) + ".jpeg"
                    if os.path.exists(filename):
                        os.remove(filename)
                    uploaded_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

                    save_local_thumbnail(toolid)

                    images_to_s3(toolid)

                    # update the database if a tool image exists
                    db.execute("UPDATE tools SET photo = :filename WHERE toolid = :toolid;", filename=filename, toolid=toolid)
                    print("Image added to database")
                else:
                    print("no tool image file found.... no updates made...")
        elif photostate == "removed": #Check if the photo was supposed to be removed.
            print("Tool owner wants the tool image removed.")

            # Delete the tool image files if stored locally
            filename_secured = UPLOAD_FOLDER + str(toolid) + ".jpeg"
            file_thumb = UPLOAD_FOLDER + str(toolid) + "_thumb.png"
            if os.path.exists(filename_secured):
                os.remove(filename_secured)
            if os.path.exists(file_thumb):
                os.remove(file_thumb)

            # Delete the tool image files if stored on aws s3:
            delete_images_s3(image_uuid)

            toolimage = "none"
            db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, photo = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, toolimage, health, features, notes, toolid)
        else: #photostate was "unchanged"
            db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, health, features, notes, toolid)


        # update the database details for the given toolid
        #db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, photo = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, toolimage, health, features, notes, toolid)

        #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("tool", "edittool", "", toolid, "", "full edit")
        flash("Successfully updated the tool")
        return redirect(url_for('tool_details') + '?toolid=' + toolid)




################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [4]   NEIGHBORHOOD MANAGEMENT                         | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

@app.route("/neighborhoods", methods=["GET", "POST"])
@login_required
def neighborhoods():
    """Show user's neighborhood page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        mynbhlist = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID) AND deleted = 0;", userUUID=userUUID)
        myneighborhoods = {}
        for row in mynbhlist:
            info = {'neighborhood': row["neighborhood"], 'neighborhoodid': row["neighborhoodid"], 'zipcode': row["zip"]}
            myneighborhoods[row["neighborhoodid"]] = info

        allnbhlist = db.execute("SELECT * FROM neighborhoods WHERE private = '0' AND deleted = 0 AND neighborhoodid NOT IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID);", userUUID=userUUID)
        allneighborhoods = {}
        for row in allnbhlist:
            info = {'neighborhood': row["neighborhood"], 'neighborhoodid': row["neighborhoodid"], 'zipcode': row["zip"]}
            allneighborhoods[row["neighborhoodid"]] = info

        return render_template("neighborhoods.html", setActive3="active", openActions=countActions(), firstname=firstname, myneighborhoods=myneighborhoods, allneighborhoods=allneighborhoods)
    else:
        # get data from the form
        neighborhoodname = request.form.get("neighborhoodname")
        # confirm that the neighborhoodname is unique (or name and zipcode)
        checkexists = db.execute("SELECT * FROM neighborhoods WHERE neighborhood = :neighborhoodname AND deleted = 0;", neighborhoodname=neighborhoodname)
        if len(checkexists) != 0:
            return apology("A neighborhood of this name already exists")
        zipcode = request.form.get("zipcode")
        private = request.form.get("private")
        password = generate_password_hash(request.form.get("password"))
        description = request.form.get("features")

        # Create the neighborhood:
        new_neighborhood_uuid = uuid.uuid4().hex
        db.execute("INSERT INTO neighborhoods (neighborhoodid, neighborhood, zip, description, private, pwd, adminuuid) VALUES (?, ?, ?, ?, ?, ?, ?);", new_neighborhood_uuid, neighborhoodname, zipcode, description, private, password, userUUID)
        # Add the user as a member to the memberships:
        #do not need: newneighborhoodid = db.execute("SELECT neighborhoodid FROM neighborhoods WHERE neighborhood IS (?);", neighborhoodname)[0]['neighborhoodid']
        db.execute("INSERT INTO memberships (useruuid, neighborhoodid, admin) VALUES (?, ?, ?);", userUUID, new_neighborhood_uuid, '1')

        # if any of the user's tools are marked as public, automatically create their tool visibility to this neighborhood.
        allmyToolsData = db.execute("SELECT * FROM tools WHERE owneruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL

        myTools = {}
        for i in range(len(allmyToolsData)):
            info = {'toolID': allmyToolsData[i]['toolid'],
                    'toolName': allmyToolsData[i]['toolname'],
                    'private': allmyToolsData[i]['private']}
            myTools[allmyToolsData[i]['toolid']] = info

        for tool in myTools:
            print(myTools[tool]['private'])
            if myTools[tool]['private'] == 0:
                exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :new_neighborhood_uuid AND toolid = :tool;", new_neighborhood_uuid=new_neighborhood_uuid, tool=tool)
                if len(exists) == 0:
                    db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", new_neighborhood_uuid, tool)
                else:
                    # tool relationship is somehow already there...
                    pass


        session["neighborhood_check"] = "1"

        #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("neighborhood", "createneighborhood", "", "", new_neighborhood_uuid, "")

        flash("Successfully created the neighborhood.")
        return redirect(url_for('neighborhoods') + '#mine')


@app.route("/neighborhood_details", methods=["GET", "POST"])
@login_required
def neighborhood_details():
    """Show user neighborhood details page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")

    if request.method == "GET":
        # Use: to get the info from the URL /neighborhood_details?neighborhoodid=3
        neighborhoodid = request.args.get("neighborhoodid")
        if not neighborhoodid:
            return apology("Must provide a neighborhood id")
        else:
            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)
            if len(neighborhooddeetz) == 0:
                # search by name
                neighborhoodfind = db.execute("SELECT * FROM neighborhoods WHERE neighborhood = :neighborhood;", neighborhood=neighborhoodid)
                if len(neighborhoodfind) == 0:
                    return apology("Could not find that neighborhood")
                else:
                    neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhood = :neighborhood;", neighborhood=neighborhoodid)
            neighborhooddeetz = neighborhooddeetz[0]
            neighborhoodid = neighborhooddeetz["neighborhoodid"]
            neighborhoodname = neighborhooddeetz["neighborhood"]
            zipcode = neighborhooddeetz["zip"]
            if neighborhooddeetz["description"]:
                description = neighborhooddeetz["description"].split('\n')
            else:
                description = ""
            if neighborhooddeetz["private"] == 0:
                privateYN = "No"
            else:
                privateYN = "Yes"
            if check_password_hash(neighborhooddeetz["pwd"], ""):
                passwordYN = "No"
            else:
                passwordYN = "Yes"
            if userUUID == neighborhooddeetz["adminuuid"]:
                yesadmin = True
            else:
                yesadmin = False
            membercount_db = db.execute("SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            membercount = len(membercount_db)
            membercheck = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid;", userUUID=userUUID, neighborhoodid=neighborhoodid)
            if len(membercheck) == 0:
                notmember = True
            else:
                notmember = False

            allmyToolsData = db.execute("SELECT * FROM tools WHERE owneruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)# removed " COLLATE NOCASE" for postgreSQL

            toolvisDB = db.execute("SELECT toolid FROM toolvisibility WHERE neighborhoodid = :neighborhoodid AND toolid IN (SELECT toolid FROM tools WHERE owneruuid = :userUUID AND deleted = 0);", neighborhoodid=neighborhoodid, userUUID=userUUID)
            toolvislist = []
            for i in toolvisDB:
                toolvislist.append(i['toolid'])

            myTools = {}
            for i in range(len(allmyToolsData)):
                if allmyToolsData[i]['toolid'] in toolvislist:
                    visible = True
                else:
                    visible = False
                info = {'toolID': allmyToolsData[i]['toolid'],
                        'toolName': allmyToolsData[i]['toolname'],
                        'isVisible': visible}
                myTools[allmyToolsData[i]['toolid']] = info

            return render_template("neighborhooddetails.html", openActions=countActions(), firstname=firstname, neighborhoodname=neighborhoodname, zipcode=zipcode, description=description, membercount=membercount, privateYN=privateYN, passwordYN=passwordYN, yesadmin=yesadmin, notmember=notmember, neighborhoodid=neighborhoodid, myTools=myTools)
    else:
        formAction = request.form.get("returnedAction")
        neighborhoodid = request.form.get("nbhid")
        if formAction == "join":
            already_member_ckeck = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid;", userUUID=userUUID, neighborhoodid=neighborhoodid)
            if len(already_member_ckeck) != 0:
                #already a member, cannot rejoin
                flash("Already a member of this neighborhood")
                return redirect(url_for('neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)[0]
            if not check_password_hash(neighborhooddeetz["pwd"], ""):
                # (if yes No password is required)
                # Neighborhood password IS required - get from form:
                neighborhoodpassword = request.form.get("password")
                if not check_password_hash(neighborhooddeetz["pwd"], neighborhoodpassword):
                    return apology("Incorrect neighborhood or password.")

            # if any of the user's tools are marked as public, automatically create their tool visibility to this neighborhood.
            allmyToolsData = db.execute("SELECT * FROM tools WHERE owneruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL

            myTools = {}
            for i in range(len(allmyToolsData)):
                info = {'toolID': allmyToolsData[i]['toolid'],
                        'toolName': allmyToolsData[i]['toolname'],
                        'private': allmyToolsData[i]['private']}
                myTools[allmyToolsData[i]['toolid']] = info

            for tool in myTools:
                if myTools[tool]['private'] == 0:
                    exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :neighborhoodid AND toolid = :tool;", neighborhoodid=neighborhoodid, tool=tool)
                    if len(exists) == 0:
                        db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", neighborhoodid, tool)

            exists = db.execute("SELECT * FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=userUUID, nbh=neighborhoodid)
            if len(exists) == 0:
                db.execute("INSERT INTO memberships (useruuid, neighborhoodid) VALUES (?, ?);", userUUID, neighborhoodid)
            session["neighborhood_check"] = "1"
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            nbhAdmin_db = db.execute("SELECT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid AND admin = 1;", neighborhoodid=neighborhoodid)
            if len(nbhAdmin_db) != 1:
                nbhAdmin = ""
            else:
                nbhAdmin = nbhAdmin_db[0]["useruuid"]
                if nbhAdmin == userUUID:
                    nbhAdmin = ""
            logHistory("neighborhood", "join", nbhAdmin, "", neighborhoodid, "")
            flash('Joined the neighborhood!')
            return redirect(url_for('neighborhoods') + '#mine')
        elif formAction == "edit":
            return redirect("/editneighborhood?neighborhoodid=" + neighborhoodid)
        elif formAction == "managemembers":
            # # TODO:
            # ensure that the current user is an admin
            return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
        elif formAction == "delete":
            #deleteneighborhood(neighborhoodid,neighborhoodid)
            return redirect("/deleteneighborhood?neighborhoodid=" + neighborhoodid)
        elif formAction == "leave":
            db.execute("DELETE FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid;", userUUID=userUUID, neighborhoodid=neighborhoodid)
            # See if the user is a member of any neighborhoods anymore - if not, set to 0
            myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID;", userUUID = session.get("user_uuid"))
            if len(myneighborhoods) != 0:
                session["neighborhood_check"] = "1"
            else:
                session["neighborhood_check"] = "0"
            nbhAdmin_db = db.execute("SELECT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid AND admin = 1;", neighborhoodid=neighborhoodid)
            if len(nbhAdmin_db) != 1:
                nbhAdmin = ""
                comment = ""
            else:
                nbhAdmin = nbhAdmin_db[0]["useruuid"]
                if nbhAdmin == userUUID:
                    nbhAdmin = ""
                    comment = "admin left"
                else:
                    comment = ""
            logHistory("neighborhood", "left", nbhAdmin, "", neighborhoodid, comment)
            flash('Left the neighborhood.')
            return redirect(url_for('neighborhoods') + '#mine')
        elif formAction == 'updatetoolvis':
            allmyToolsData = db.execute("SELECT * FROM tools WHERE owneruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL

            toolvisDB = db.execute("SELECT toolid FROM toolvisibility WHERE neighborhoodid = :neighborhoodid AND toolid IN (SELECT toolid FROM tools WHERE owneruuid = :userUUID AND deleted = 0);", neighborhoodid=neighborhoodid, userUUID=userUUID)
            toolvislist = []
            for i in toolvisDB:
                toolvislist.append(i['toolid'])

            myTools = {}
            for i in range(len(allmyToolsData)):
                info = {'toolID': allmyToolsData[i]['toolid'],
                        'toolName': allmyToolsData[i]['toolname']}
                myTools[allmyToolsData[i]['toolid']] = info

            toolvisibilityUpdates = request.form.get("toolvis")
            if toolvisibilityUpdates == "":
                # all tools need to be removed from this nbh
                tool_include_list = []
            else:
                tool_include_list = toolvisibilityUpdates.split(',')

            for tool in myTools:
                #print(tool)
                #print()
                if tool in tool_include_list:
                    exists = db.execute("SELECT * FROM toolvisibility WHERE neighborhoodid = :neighborhoodid AND toolid = :tool;", neighborhoodid=neighborhoodid, tool=tool)
                    if len(exists) == 0:
                        db.execute("INSERT INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", neighborhoodid, tool)
                else:
                    db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :neighborhoodid AND toolid = :toolid;", neighborhoodid=neighborhoodid, toolid=tool)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("neighborhood", "edittool", "", "", neighborhoodid, "updated tool visibilities")
            flash('Updated tool visibilities.')
            return redirect("/neighborhood_details?neighborhoodid=" + neighborhoodid)

        elif formAction == "cancel":
            return redirect(url_for('neighborhoods') + '#mine')
        else:
            return apology("Misc Error")


@app.route("/managemembers", methods=["GET", "POST"])
@login_required
@neighborhood_required
def managemembers():
    """Show user neighborhood details page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")

    if request.method == "GET":
        # Use: to get the info from the URL /neighborhood_details?neighborhoodid=3
        neighborhoodid = request.args.get("neighborhoodid")
        if not neighborhoodid:
            return apology("Must provide a neighborhood id")
        else:
            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)
            if len(neighborhooddeetz) == 0:
                # search by name
                neighborhoodfind = db.execute("SELECT * FROM neighborhoods WHERE neighborhood = :neighborhood;", neighborhood=neighborhoodid)
                if len(neighborhoodfind) == 0:
                    return apology("Could not find that neighborhood")
                else:
                    neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhood = :neighborhood;", neighborhood=neighborhoodid)
            neighborhooddeetz = neighborhooddeetz[0]
            neighborhoodid = neighborhooddeetz["neighborhoodid"]
            neighborhoodname = neighborhooddeetz["neighborhood"]
            # todo: ensure the user is an admin of the neighborhood
            memberlist_db = db.execute("SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            membercount = len(memberlist_db)
            allMembers = {}
            for i in range(len(memberlist_db)):
                memberinfo = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=memberlist_db[i]['useruuid'])[0]
                info = {"uuid": memberlist_db[i]['useruuid'],
                        "username": memberinfo['username'],
                        "firstname": memberinfo['firstname']}
                allMembers[memberlist_db[i]['useruuid']] = info

            bannedlist_db = db.execute("SELECT DISTINCT useruuid FROM membershipbans WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            bannedUsers = {}
            for i in range(len(bannedlist_db)):
                banneduserinfo = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=bannedlist_db[i]['useruuid'])[0]
                info = {"uuid": bannedlist_db[i]['useruuid'],
                        "username": banneduserinfo['username'],
                        "firstname": banneduserinfo['firstname']}
                bannedUsers[bannedlist_db[i]['useruuid']] = info

            return render_template("managemembers.html", openActions=countActions(), firstname=firstname, neighborhoodname=neighborhoodname, membercount=membercount, neighborhoodid=neighborhoodid, allMembers=allMembers, bannedUsers=bannedUsers)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "sendMail":
            neighborhoodid = request.form.get("nbhid")
            #todo: ensure user is an admin
            return redirect(f"/sendmail?neighborhoodid={neighborhoodid}")
        elif formAction == "cancel":
            return redirect("/findtool")
        else:
            return apology("Misc Error")


@app.route("/editneighborhood", methods=["GET", "POST"])
@login_required
#@neighborhood_required
def editneighborhood():
    """Show user edit neighborhood page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        neighborhoodid = request.args.get("neighborhoodid")
        if not neighborhoodid:
            return apology("Need to provide a neighborhood id")

        neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]

        if userUUID != neighborhooddeetz["adminuuid"]:
            # The active user is not the neighborhood admin
            flash("UNAUTHORIZED - cannot edit the neighborhood if not the admin.")
            return redirect(url_for('neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

        neighborhood = neighborhooddeetz["neighborhood"]
        zipcode = neighborhooddeetz["zip"]
        description = neighborhooddeetz["description"]
        privateCheck = neighborhooddeetz["private"]
        if check_password_hash(neighborhooddeetz["pwd"], ""):
            passwordYN = "No"
        else:
            passwordYN = "Yes"

        return render_template("editneighborhood.html", openActions=countActions(), firstname=firstname, neighborhood=neighborhood, zipcode=zipcode, description=description, privateCheck=privateCheck, passwordYN=passwordYN, neighborhoodid=neighborhoodid)
    else:
        neighborhoodid = request.form.get("neighborhoodid")
        neighborhood = request.form.get("neighborhood")
        private = request.form.get("private")
        zipcode = request.form.get("zipcode")
        description = request.form.get("description")
        password = generate_password_hash(request.form.get("password"))

        # update the database details for the given neighborhoodid
        db.execute("UPDATE neighborhoods SET neighborhood = ?, private = ?, zip = ?, description = ?, pwd = ? WHERE neighborhoodid = ?;", neighborhood, private, zipcode, description, password, neighborhoodid)
        #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("neighborhood", "editneighborhood", "", "", neighborhoodid, "Neighborhood edited")
        flash("Successfully updated the neighborhood")
        return redirect(url_for('neighborhoods') + '#mine')


@app.route("/deleteneighborhood", methods=["GET", "POST"])
@login_required
#@neighborhood_required
def deleteneighborhood():
    """confirm account deletion"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        neighborhoodid = request.args.get("neighborhoodid")
        neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]
        neighborhoodname = neighborhooddeetz['neighborhood']
        #confirm that the active user is an admin for the neighborhood, otherwise return unauthorized
        if userUUID != neighborhooddeetz["adminuuid"]:
            # The active user is not the neighborhood admin
            flash("UNAUTHORIZED - cannot delete the neighborhood if not the admin.")
            return redirect(url_for('neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

        return render_template("confirmdelete_nbh.html", openActions=countActions(), firstname=firstname, neighborhoodname=neighborhoodname, neighborhoodid=neighborhoodid)
    else:
        formAction = request.form.get("returnedAction")
        neighborhoodid = request.form.get("neighborhoodid")
        if formAction == "deleteNeighborhood":
            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]
            if userUUID != neighborhooddeetz["adminuuid"]:
                # The active user is not the neighborhood admin
                flash("UNAUTHORIZED - cannot delete the neighborhood if not the admin.")
                return redirect(url_for('neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

            # first confirm password...
            password = request.form.get("password")
            if not password:
                return apology("You must enter your password to delete the neighborhood", "403")
            # current password
            getCurrPW = db.execute("SELECT hash FROM users WHERE uuid = :userUUID", userUUID=userUUID)
            if len(getCurrPW) != 1 or not check_password_hash(getCurrPW[0]["hash"], password):
                return apology("Incorrect password", 403)

            # execute the following to "delete" the user.  The delete is just a soft delete.
            db.execute("UPDATE neighborhoods SET deleted = 1 WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            # remove all members (this is a permanent delete)
            db.execute("DELETE FROM memberships WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("neighborhood", "deleteneighborhood", "", "", neighborhoodid, "")
            flash('Neighborhood deleted.')
            return redirect(url_for('neighborhoods') + '#mine')
        elif formAction == "cancel":
            return render_template("swipepage.html")
            #return redirect("/neighborhood_details?neighborhoodid=" + neighborhoodid)
        else:
            return apology("Misc Error")


@app.route("/sendmail", methods=["GET", "POST"])
@login_required
@neighborhood_required
def sendmail():
    """confirm account deletion"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        neighborhoodid = request.args.get("neighborhoodid")
        if neighborhoodid:
            #todo: ensure user is an admin
            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)[0]
            neighborhoodName = neighborhooddeetz['neighborhood']
            userdeetz = db.execute("SELECT * FROM users WHERE uuid = :userUUID", userUUID=userUUID)[0]
            username = userdeetz['username']
            email = userdeetz['email']
            return render_template("sendmail.html", openActions=countActions(), firstname=firstname, username=username, email=email, neighborhoodName=neighborhoodName, askall=False, neighborhood_send_list=neighborhoodid)

        mynbhlist = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID) AND deleted = 0;", userUUID=userUUID)
        myneighborhoods = {}
        for row in mynbhlist:
            info = {'neighborhood': row["neighborhood"], 'neighborhoodid': row["neighborhoodid"]}
            myneighborhoods[row["neighborhoodid"]] = info
        userdeetz = db.execute("SELECT * FROM users WHERE uuid = :userUUID", userUUID=userUUID)[0]
        username = userdeetz['username']
        email = userdeetz['email']
        return render_template("sendmail.html", openActions=countActions(), firstname=firstname, myneighborhoods=myneighborhoods, username=username, email=email, askall=True)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "sendMail":
            nbhChecks = request.form.getlist("nbhChecks")
            shareChecks = request.form.getlist("shareChecks")
            if len(nbhChecks) == 0:
                neighborhood_send_list = request.form.get("neighborhood_send_list")
                if neighborhood_send_list == "":
                    flash("You must pick at least one neighborhood.")
                    return apology("one neighborhood", "you must pick at least one")

                #send the email to the one preloaded into the form (admin mail)
                #todo: ensure user is an admin
                print("Admin email to: " + neighborhood_send_list)
            else:
                ## TODO: for each NBH, ensure the user is a member
                print("Asking these neighborhoods: " + str(nbhChecks))
            if "email" in shareChecks:
                print("YES: share the email address")
            else:
                print("NO: don't share the email address")
            return apology("todo")
        elif formAction == "cancel":
            return redirect("/findtool")
        else:
            return apology("Misc Error")



################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [5]   USER MANAGEMENT                                 | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_uuid
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username or email", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        next_url = request.form.get("next")
        print(next_url)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username OR email = :username;",
                          username=request.form.get("username").lower())

        # Ensure username exists and password is correct and the account isn't soft-deleted
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")) or rows[0]["deleted"] == 1:
            #logHistory("other", "failedlogin1", "", "", "", "")
            #db.execute("INSERT INTO history (type, action, useruuid, timestamp) VALUES (?, ?, ?, ?);", "other", "failedlogin1", "unknown", datetime.datetime.now())
            return apology("invalid username and/or password. To recover your account contact the admin.", 403)

        # This is being taken care of in the catch-all above
        if rows[0]["deleted"] == 1:
            #logHistory("other", "failedlogin2", "", "", "", "")
            #db.execute("INSERT INTO history (type, action, useruuid, timestamp) VALUES (?, ?, ?, ?);", "other", "failedlogin2", "unknown", datetime.datetime.now())
            return apology("This accound has been shutdown. Contact admin to reactivate.", 423)

        if rows[0]["validateemail"] != "":
            flash("Please validate your email.")
            return redirect(f"/validateemail?email={rows[0]['email']}")

        # If the user had requested a password reset, but then logs in, clear their recoverykey
        db.execute("UPDATE users SET recoverykey = '' WHERE uuid = :userUUID;", userUUID=rows[0]["uuid"])

        # Remember which user has logged in
        session["user_uuid"] = rows[0]["uuid"]
        session["firstname"] = rows[0]["firstname"]
        session["theme"] = rows[0]["theme"]

        # See if the user is a member of any neighborhoods
        myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID;", userUUID = session.get("user_uuid"))
        if len(myneighborhoods) != 0:
            session["neighborhood_check"] = "1"
        else:
            session["neighborhood_check"] = "0"

        #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("other", "login", "", "", "", "")

        # Redirect user to home page
        flash('You were successfully logged in.')
        if next_url:
            return redirect(next_url)
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        #logHistory("other", "pagevisit", "", "", "", "")
        #db.execute("INSERT INTO history (type, action, useruuid, timestamp) VALUES (?, ?, ?, ?);", "other", "pagevisit", "unknown", datetime.datetime.now())
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
    logHistory("other", "logout", "", "", "", "")
    # Forget any user_uuid
    session.clear()
    # Redirect user to login form
    flash('You were successfully logged out.')
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        firstname = request.form.get("firstname")
        newUsername = request.form.get("username").lower()
        email = request.form.get("email").lower()
        password1 = request.form.get("password")
        password2 = request.form.get("confirmation")
        # Confirm the user entered something into the firstname field
        if not firstname:
            return apology("You must enter your first name", "Sorry")
        # Confirm the user entered something into the username field
        if not newUsername:
            return apology("You must enter a username", "Sorry")
        # Confirm that the two passwords match
        if password1 != password2:
            return apology("Your password entries do not match", "Sorry")
        # Check if username is already in the users table
        rows1 = db.execute("SELECT uuid FROM users WHERE username = ?;", newUsername)
        if len(rows1) != 0:
            return apology("This username already exists", "Sorry")

        rows2 = db.execute("SELECT uuid FROM users WHERE email = ?;", email)
        if len(rows2) != 0:
            return apology("Try the forgot password option", "Email in use already")

        # generate a new UUID for the user
        new_uuid = uuid.uuid4().hex
        # generate uuid for email opt-out.
        optouttoken = uuid.uuid4().hex
        # Initiate the user with an unregistered_email:
        db.execute("INSERT INTO users (uuid, firstname, username, email, hash, validateemail, email_optout) VALUES (?, ?, ?, ?, ?, ?, ?);", new_uuid, firstname, newUsername, email, generate_password_hash(password1), "unregistered_email", optouttoken)
        #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        db.execute("INSERT INTO history (type, action, useruuid, comment, timestamp) VALUES (?, ?, ?, ?, ?);", "other", "signup", new_uuid, "NEW USER!!", datetime.datetime.now())

        authcode = generate_new_authcode(email)

        session["firstname"] = firstname

        return redirect(f"/validateemail?email={email}")


@app.route("/validateemail", methods=["GET", "POST"])
def validateemail():
    code_timeout_limit = 2#minutes
    if session.get("user_uuid") is not None:
        flash("Already logged in...")
        return redirect("/")
    if request.method == "GET":
        new_email = request.args.get("email")
        error = request.args.get("error")
        if new_email == "":
            return apology("not found","404")
        new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
        if len(new_user) != 1:
            return apology("No user found")
        elif new_user[0]['validateemail'] == "":
            flash("Email already validated")
            return redirect("/")
        #get the user's autorization code:
        fullcodedetails = new_user[0]['validateemail'].split(";")
        valid_code = fullcodedetails[1]
        start_timestamp = datetime.datetime.strptime(fullcodedetails[2], '%Y-%m-%d %H:%M:%S.%f')
        validate_timestamp = datetime.datetime.now()
        time_dif = validate_timestamp - start_timestamp
        time_dif_minutes = time_dif.total_seconds() / 60
        if time_dif_minutes > code_timeout_limit:
            # authorization code expired, new authcode and send email
            authcode = generate_new_authcode(new_email)
            error = "timeout"
            return redirect(f"/validateemail?email={new_email}&error={error}")

        # If the authcode was sent with the url (GET), this would be the case if the user clicks the email link
        authcode = request.args.get("authcode")
        if authcode != None:
            authcode = authcode.upper()
            if authcode == valid_code:
                # accound validated
                db.execute("UPDATE users SET validateemail = '' WHERE uuid = :uuid", uuid=new_user[0]['uuid'])
                session["user_uuid"] = new_user[0]["uuid"]
                session["firstname"] = new_user[0]["firstname"]
                session["neighborhood_check"] = "0"
                logHistory("other", "email_validated", "", "", "", "")
                # redirect back to the index (root) page
                flash(new_user[0]["firstname"] + ", your email has been validated.")
                return redirect("/")
            else:
                error = "incorrect"
                return redirect(f"/validateemail?email={new_email}&error={error}")

        errormessage = ""
        error = request.args.get("error")
        if error != None:
            if error == "":
                errormessage = ""
            elif error == "timeout":
                errormessage = "Your prior code has expired, please check your email for a new one."
            elif error == "incorrect":
                errormessage = "Incorrect authorization code. Please try again."
        return render_template("validateemail.html", new_email=new_email, errormessage=errormessage)
    else:#POST
        formAction = request.form.get("returnedAction")
        new_email = request.form.get("useremail")
        if formAction == "resendCode":
            new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
            if len(new_user) != 1:
                return apology("Error: No user found")
            elif new_user[0]['validateemail'] == "":
                flash("Email already validated")
                return redirect("/")
            # resend new user confirmation
            # get a new authcode (and set it in the db and send email)
            authcode = generate_new_authcode(new_email)
            flash("New authorization code has been emailed.")
            return redirect(f"/validateemail?email={new_email}")
        elif formAction == "confirmAccount":
            # get the form data
            input_authcode = request.form.get("authcode").upper()
            new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
            if len(new_user) != 1:
                return apology("Error: No user found")
            elif new_user[0]['validateemail'] == "":
                flash("Email already validated")
                return redirect("/")
            #get the user's autorization code:
            fullcodedetails = new_user[0]['validateemail'].split(";")
            valid_code = fullcodedetails[1]
            start_timestamp = datetime.datetime.strptime(fullcodedetails[2], '%Y-%m-%d %H:%M:%S.%f')
            validate_timestamp = datetime.datetime.now()
            time_dif = validate_timestamp - start_timestamp
            time_dif_minutes = time_dif.total_seconds() / 60
            if time_dif_minutes > code_timeout_limit:
                # authorization code expired, new authcode and send email
                authcode = generate_new_authcode(new_email)

                errormessage = "Your prior code has expired, please check your email for a new one."
                return render_template("validateemail.html", new_email=new_email, errormessage=errormessage)
            if input_authcode == valid_code:
                # accound validated
                send_email_welcome(new_email, new_user[0]["firstname"])
                db.execute("UPDATE users SET validateemail = '' WHERE uuid = :uuid", uuid=new_user[0]['uuid'])
                session["user_uuid"] = new_user[0]["uuid"]
                session["firstname"] = new_user[0]["firstname"]
                session["neighborhood_check"] = "0"
                logHistory("other", "email_validated", "", "", "", "")
                # redirect back to the index (root) page
                flash(new_user[0]["firstname"] + ", your email has been validated.")
                return redirect("/")
            else:
                error = "incorrect"
                return redirect(f"/validateemail?email={new_email}&error={error}")

        else:
            return apology("Misc Error")


@app.route("/manageaccount", methods=["GET", "POST"])
@login_required
def manageaccount():
    """Delete account, change password, etc"""
    userUUID = session.get("user_uuid")
    miscInfo = db.execute("SELECT firstname, username, email FROM users WHERE uuid = :userUUID;", userUUID=userUUID)[0]
    firstname = miscInfo["firstname"]
    username = miscInfo["username"]
    email = miscInfo["email"]
    scrollPos = 0
    if request.method == "GET":
        return render_template("manageaccount.html", openActions=countActions(), firstname=firstname, username=username, email=email, scrollPos=scrollPos)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "changeName":
            return redirect("/changename")
        elif formAction == "changePassword":
            return redirect("/changepassword")
        elif formAction == "updateEmail":
            return redirect("/updateemail")
        elif formAction == "commPrefs":
            return redirect("/communication")
        elif formAction == "viewHistory":
            return redirect("/history")
        elif formAction == "deleteAccount":
            return redirect("/deleteaccount")
        elif formAction == "returnHome":
            return redirect("/")
        elif formAction == "toggleTheme":
            if session["theme"] == "light":
                session["theme"] = "dark"
            else:
                session["theme"] = "light"
            #set the preference for the user
            db.execute("UPDATE users SET theme = :newTheme WHERE uuid = :userUUID;", userUUID=userUUID, newTheme=session["theme"])
            scrollPos = request.form.get("pageoffset")
            return render_template("manageaccount.html", openActions=countActions(), firstname=firstname, username=username, email=email, scrollPos=scrollPos)
        else:
            return apology("Misc Error")


@app.route("/communication", methods=["GET", "POST"])
#@login_required <--managed internally
def communication():
    '''Update communication preferences'''
    if request.method == "GET":
        email = request.args.get("email")
        optouttoken = request.args.get("optout")
        if email != None:
            if optouttoken != None:
                #check if opt-out token matches the one in the user's account
                userdeetz = db.execute("SELECT * FROM users WHERE email = :email", email=email)
                if len(userdeetz) == 1:#a user exists with this email
                    if "optin" in userdeetz[0]['emaillevel'].split(","):#if the user is still opted in
                        if userdeetz[0]['email_optout'] == optouttoken:
                            existing_mail_pref = userdeetz[0]['emaillevel'].split(",")
                            new_mail_pref = ""
                            for i in existing_mail_pref:
                                if i == "optin":
                                    new_mail_pref += "optout,"
                                elif i == "":
                                    pass
                                else:
                                    new_mail_pref += i
                            db.execute("UPDATE users SET emaillevel = :new_mail_pref WHERE uuid = :userUUID;", userUUID=userdeetz[0]['uuid'], new_mail_pref=new_mail_pref)
                            #if user is logged in, flash and redirect to communication Preferences
                            if session.get("user_uuid") is not None:
                                flash("You have been unsubscribed")
                                userUUID = session.get("user_uuid")
                                firstname = session.get("firstname")
                                return render_template("communicationpreferences.html", openActions=countActions(), firstname=firstname)
                            else:
                                return render_template("unsubscribed.html")
                        else:
                            return apology("Invalid opt-out token", "contact admin")
                    else:
                        #user was already opted out
                        if session.get("user_uuid") is not None:
                            flash("You have already opted out.")
                            userUUID = session.get("user_uuid")
                            firstname = session.get("firstname")
                            return render_template("communicationpreferences.html", openActions=countActions(), firstname=firstname)
                        else:
                            return redirect("/login")
                else:
                    #user does not exist...
                    return redirect("/")
        #email or optouttoken not provided
        if session.get("user_uuid") is not None:
            userUUID = session.get("user_uuid")
            firstname = session.get("firstname")
            #get the user communication preferences
            userdeetz = db.execute("SELECT * FROM users WHERE uuid = :userUUID", userUUID=userUUID)[0]
            phonenumber = userdeetz['phonenumber']
            phonepref = userdeetz['phonepref']#none/call/sms/both
            if phonepref == "none":
                phonenumber = ""
            emaillevel = userdeetz['emaillevel'].split(",")#optin/optout,nbh
            if "nbh" in emaillevel:
                nbhemails = True
            else:
                nbhemails = False
            if "optout" in emaillevel:
                optout = True
            else:
                optout = False
            return render_template("communicationpreferences.html", openActions=countActions(), firstname=firstname, optout=optout, phonenumber=phonenumber, phonepref=phonepref, nbhemails=nbhemails)
        else:
            return redirect("/login")
    else: #POST
        #@login_required
        if session.get("user_uuid") is None:
            return redirect("/login")

        userUUID = session.get("user_uuid")
        formAction = request.form.get("returnedAction")
        if formAction == "returnHome":
            return redirect("/manageaccount")
        elif formAction == "saveChanges":
            # get the form data
            allchecks = request.form.getlist("allchecks")
            new_mail_pref = ""
            if 'optin' in allchecks:
                new_mail_pref += 'optin,'
            else:
                new_mail_pref += 'optout,'
            if 'nbh' in allchecks:
                new_mail_pref += 'nbh'
            db.execute("UPDATE users SET emaillevel = :emaillevel WHERE uuid = :userUUID;", userUUID=userUUID, emaillevel=new_mail_pref)
            if 'phoneyes' in allchecks:
                phone_number = request.form.get("phone_number")
                print(phone_number)
                if phone_number == "":
                    flash("Please add a phone number.")
                    return redirect("/communication")
                if (('call' not in allchecks) and ('sms' not in allchecks)):
                    return apology("phonr contact type error")
                if 'call' in allchecks:
                    if 'sms' in allchecks:
                        #both
                        db.execute("UPDATE users SET phonepref = 'both', phonenumber = :phonenumber WHERE uuid = :userUUID;", userUUID=userUUID, phonenumber=phone_number)
                    else:
                        #call only
                        db.execute("UPDATE users SET phonepref = 'call', phonenumber = :phonenumber WHERE uuid = :userUUID;", userUUID=userUUID, phonenumber=phone_number)
                else:
                    #sms only
                    db.execute("UPDATE users SET phonepref = 'sms', phonenumber = :phonenumber WHERE uuid = :userUUID;", userUUID=userUUID, phonenumber=phone_number)
            else:
                #set the user's phone preference to 'none'
                db.execute("UPDATE users SET phonepref = 'none' WHERE uuid = :userUUID;", userUUID=userUUID)
            flash("Your communication preferences have been saved.")
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editcommprefs", "", "", "", "")
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@app.route("/changepassword", methods=["GET", "POST"])
#@login_required <--managed internally
def changepassword():
    """change your password"""
    if request.method == "GET":
        verb = "Change"
        # If the user is not logged in, check if they are passing in email and recovery token for password recovery
        if session.get("user_uuid") is None:
            email = request.args.get("email")
            recoverytoken = request.args.get("recoverytoken")
            if email != None:
                userdeetz = db.execute("SELECT * FROM users WHERE email = :email", email=email)
                if len(userdeetz) == 1:
                    if (userdeetz[0]['recoverykey'] != "") and (recoverytoken != None):
                        if userdeetz[0]['recoverykey'] == recoverytoken:
                            verb = "New"
                            return render_template("updatepwd.html", recoverytoken=recoverytoken, email=email, verb=verb)
                        else:
                            flash("Password reset link has expired.")
            return redirect(url_for("login"))
        else:
            userUUID = session.get("user_uuid")
            firstname = session.get("firstname")
            email = request.args.get("email")
            recoverytoken = request.args.get("recoverytoken")
            if ((email != None) or (recoverytoken != None)):
                flash("Already logged in, no password reset needed.")
                db.execute("UPDATE users SET recoverykey = '' WHERE uuid = :userUUID;", userUUID=userUUID)
                return redirect("/")
            return render_template("updatepwd.html", openActions=countActions(), verb=verb, firstname=firstname)
    else:
        #todo add in the recovery key check and if valid, change password, login the user (set session), reset recoverykey, redirecto to "/"
        formAction = request.form.get("returnedAction")
        if formAction == "returnHome":
            return redirect("/manageaccount")
        elif formAction == "changePassword":
            # get the form data
            oldPassword = request.form.get("oldPassword")
            newPassword1 = request.form.get("newPassword1")
            newPassword2 = request.form.get("newPassword2")
            if oldPassword == None:
                # password recovery via token:
                # confirm token:
                recoverytoken = request.form.get("recoverytoken")
                email = request.form.get("email")
                userdeetz = db.execute("SELECT * FROM users WHERE email = :email", email=email)
                if len(userdeetz) != 0:
                    if userdeetz[0]['recoverykey'] != recoverytoken:
                        return apology("Misc error")#token doesnt match
                #user exists and the tken matches:
                # ensure fields are all provided
                if not newPassword1 or not newPassword2:
                    return apology("You must enter all of the password fields", "403")
                # confirm both new passwords are the same
                if newPassword1 != newPassword2:
                    return apology("Your new password entries do not match", "403")
                # clear their recoverykey
                db.execute("UPDATE users SET recoverykey = '' WHERE uuid = :userUUID;", userUUID=userdeetz[0]["uuid"])
                # go agead and log the user in at this point
                session["user_uuid"] = userdeetz[0]["uuid"]
                session["firstname"] = userdeetz[0]["firstname"]
                # See if the user is a member of any neighborhoods
                myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID;", userUUID = session.get("user_uuid"))
                if len(myneighborhoods) != 0:
                    session["neighborhood_check"] = "1"
                else:
                    session["neighborhood_check"] = "0"
                # Update the user's password
                db.execute("UPDATE users SET hash = :newPW WHERE uuid = :userUUID;",
                           newPW=generate_password_hash(newPassword1), userUUID=session["user_uuid"])
                #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
                logHistory("other", "recoveredpassword", "", "", "", "")
                flash('Your password was reset.')
                return redirect("/")

            #ELSE, the user was just changing their password
            if session.get("user_uuid") is None:
                return redirect(url_for("login"))
            userUUID = session.get("user_uuid")
            firstname = session.get("firstname")
            # ensure fields are all provided
            if not oldPassword or not newPassword1 or not newPassword2:
                return apology("You must enter all of the password fields", "403")
            # confirm both new passwords are the same
            if newPassword1 != newPassword2:
                return apology("Your new password entries do not match", "403")
            if oldPassword == newPassword1:
                return apology("Your new password must be different", "403")
            # confirm "oldPassword" is correct
            oldPWHash = db.execute("SELECT hash FROM users WHERE uuid = :userUUID", userUUID=userUUID)
            if len(oldPWHash) != 1 or not check_password_hash(oldPWHash[0]["hash"], oldPassword):
                return apology("Current password check fail", 403)
            # Update the user's password
            db.execute("UPDATE users SET hash = :newPW WHERE uuid = :userUUID;",
                       newPW=generate_password_hash(newPassword1), userUUID=userUUID)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editpassword", "", "", "", "")
            # show confirmation to user
            flash('Password successfully updated.')
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@app.route("/changename", methods=["GET", "POST"])
@login_required
def changename():
    """change your firstname"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        return render_template("updatename.html", openActions=countActions(), firstname=firstname)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "returnHome":
            return redirect("/manageaccount")
        elif formAction == "changename":
            # get the form data
            newName = request.form.get("newName")
            if not newName:
                flash('Must enter a name.')
                return render_template("updatename.html", openActions=countActions(), firstname=firstname)
            if newName == firstname:
                flash('that is not a new name...')
                return render_template("updatename.html", openActions=countActions(), firstname=firstname)

            # Update the user's name
            db.execute("UPDATE users SET firstname = :newName WHERE uuid = :userUUID;", newName=newName, userUUID=userUUID)
            session["firstname"] = newName
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editusername", "", "", "", "")
            # show confirmation to user
            flash('Name changed successfully.')
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@app.route("/updateemail", methods=["GET", "POST"])
@login_required
def updateemail():
    """change your email"""
    userUUID = session.get("user_uuid")
    miscInfo = db.execute("SELECT firstname, email FROM users WHERE uuid = :userUUID;", userUUID=userUUID)[0]
    firstname = miscInfo["firstname"]
    oldEmail = miscInfo["email"]
    if request.method == "GET":
        return render_template("updateemail.html", openActions=countActions(), firstname=firstname, oldEmail=oldEmail)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "returnHome":
            return redirect("/manageaccount")
        elif formAction == "changeEmail":
            # get the form data
            newEmail = request.form.get("newEmail")
            if newEmail == "":
                flash('Must enter an email address.')
                return render_template("updateemail.html", openActions=countActions(), firstname=firstname, oldEmail=oldEmail)
            if newEmail == oldEmail:
                flash("that's the same email address...")
                return render_template("updateemail.html", openActions=countActions(), firstname=firstname, oldEmail=oldEmail)

            # Update the user's email
            db.execute("UPDATE users SET email = :newEmail WHERE uuid = :userUUID;", newEmail=newEmail, userUUID=userUUID)

            #require the user validate the new email address:
            authcode = generate_new_authcode(newEmail)

            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editemail", "", "", "", "")
            # show confirmation to user
            session.clear()
            session["firstname"] = firstname
            #flash('Email changed successfully.')
            return redirect(f"/validateemail?email={newEmail}")
        else:
            return apology("Misc Error")


@app.route("/deleteaccount", methods=["GET", "POST"])
@login_required
def deleteaccount():
    """confirm account deletion"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        return render_template("confirmdelete.html", openActions=countActions(), firstname=firstname)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "deleteAccount":
            # first confirm password...
            password = request.form.get("password")
            if not password:
                return apology("You must enter your password to delete your account", "403")
            # current password
            getCurrPW = db.execute("SELECT hash FROM users WHERE uuid = :userUUID", userUUID=userUUID)
            if len(getCurrPW) != 1 or not check_password_hash(getCurrPW[0]["hash"], password):
                return apology("Incorrect password", 403)

            # execute the following to "delete" the user.  The delete is just a soft delete.
            db.execute("UPDATE users SET deleted = 1 WHERE uuid = :userUUID;", userUUID=userUUID)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "deleteuser", "", "", "", "")
            session.clear()
            flash('Your account was deleted.')
            return apology("to see you go!", "sorry")
        elif formAction == "returnHome":
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    """Show history of all tool and neighborhood related actions of the user"""

    if request.method == "GET":
        toolhistoryDB = db.execute("SELECT * FROM history WHERE type = 'tool' AND (useruuid = :userUUID OR seconduuid = :userUUID);", userUUID=userUUID)
        counter = 1
        toolhistory = {}
        for event in toolhistoryDB[::-1]:#itearate through in reverse order
            refnumber = counter
            d = datetime.datetime.strptime(event["timestamp"], '%Y-%m-%d %H:%M:%S')
            date = d.strftime('%b %d')
            timestamp = d.strftime('%H:%M:%S - %b %d, %Y (UTC)')
            action = event["action"]
            toolid = event["toolid"]
            toolname_db = db.execute("SELECT toolname FROM tools WHERE toolid = :toolid;", toolid=toolid)
            if len(toolname_db) != 0:
                toolname = toolname_db[0]['toolname']
            else:
                toolname = "Tool no longer exists: (ID:" + toolid + ")"
            comment = event["comment"]
            firstuuid = event["useruuid"]
            firstuser = ""
            seconduuid = event["seconduuid"]
            seconduser = ""
            if firstuuid != "":
                firstuser = db.execute("SELECT username FROM users WHERE uuid = :uuid;", uuid=firstuuid)[0]['username']
            if seconduuid != "":
                seconduser = db.execute("SELECT username FROM users WHERE uuid = :uuid;", uuid=seconduuid)[0]['username']

            description = getDescriptionTool(action, firstuser, seconduser, comment)
            counter += 1
            info = {"refnumber": refnumber, "date": date, "timestamp": timestamp, "action": action, "toolid": toolid, "toolname": toolname, "comment": description}
            toolhistory[refnumber] = info

        nbhhistoryDB = db.execute("SELECT * FROM history WHERE type = 'neighborhood' AND (useruuid = :userUUID OR seconduuid = :userUUID);", userUUID=userUUID)
        counter = 1
        nbhhistory = {}
        for event in nbhhistoryDB[::-1]:#itearate through in reverse order
            refnumber = counter
            d = datetime.datetime.strptime(event["timestamp"], '%Y-%m-%d %H:%M:%S')
            date = d.strftime('%b %d')
            timestamp = d.strftime('%H:%M:%S - %b %d, %Y (UTC)')
            action = event["action"]
            neighborhoodid = event["neighborhoodid"]
            neighborhoodname = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)[0]['neighborhood']
            comment = event["comment"]
            firstuuid = event["useruuid"]
            firstuser = ""
            seconduuid = event["seconduuid"]
            seconduser = ""
            if firstuuid != "":
                firstuser = db.execute("SELECT username FROM users WHERE uuid = :uuid;", uuid=firstuuid)[0]['username']
            if seconduuid != "":
                seconduser = db.execute("SELECT username FROM users WHERE uuid = :uuid;", uuid=seconduuid)[0]['username']

            description = getDescriptionNBH(action, firstuser, seconduser, comment)
            counter += 1
            info = {"refnumber": refnumber, "date": date, "timestamp": timestamp, "action": action, "neighborhoodid": neighborhoodid, "neighborhoodname": neighborhoodname, "comment": description}
            nbhhistory[refnumber] = info

        return render_template("history.html", openActions=countActions(), firstname=firstname, toolhistory=toolhistory, nbhhistory=nbhhistory)

    else:
        pass


@app.route("/passwordrecovery", methods=["GET", "POST"])
def passwordrecovery():
    """Password Recovery"""
    if session.get("user_uuid") is not None:
        flash("Already logged in...")
        return redirect("/manageaccount")
    if request.method == "GET":
        return render_template("passwordrecovery.html")
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "resetPW":
            # first confirm that the email address is linked to an active user
            email = request.form.get("email")
            userdeetz = db.execute("SELECT * FROM users WHERE email = :email", email=email)
            if len(userdeetz) != 1:
                # no email with this account... but don't release this information
                return render_template("passwordrecoverysent.html")
                #return apology("email check fail")

            # generate new recovery key, and set it to the user
            recoverykey = uuid.uuid4().hex
            db.execute("UPDATE users SET recoverykey = :key WHERE uuid = :userUUID;", key=recoverykey, userUUID=userdeetz[0]["uuid"])

            # send email with authcode
            recipients = [userdeetz[0]["email"]]
            subject = "ToolShare Password Reset"
            message = f"""\
                        <html style="font-family: arial; background-color: lightgray;">
                          <head>
                            <title>Tool Share - Password Recovery</title>
                          </head>

                          <body style="margin: 0; background-color: white; border: 7px solid lightgray; position: absolute; top: 0; left: 0;">
                            <div style="width: 100%; background-color: #f8f9fa;">
                              <a href="https://sharetools.tk"><img src="https://i.imgur.com/dzuJftm.png" alt=""></a>
                            </div>
                            <div style="padding: 20px 10px 30px 10px; background-color: white; ">
                              In order to reset the password to your ToolShare account, please click the link below<br>
                              <span style="font-size: small;">If you did not request this password change, please log back in to confirm your account.</span>
                              <div style="padding: 25px;">
                                <span style="padding-left: 12px;">
                                  <a href="https://sharetools.tk/changepassword?email={email}&recoverytoken={recoverykey}">Reset my password</a>.
                                </span>
                              </div>
                            </div>
                            <div style="padding: 8px; position: fixed; bottom: 0; left: 0; width: 100%;">
                              <div style="font-size: 10px; color: gray; text-align: center; width: 100%;">
                                Copyright 2021 / Steven Small / All Rights Reserved
                              </div>
                            </div>
                          </body>
                        </html>
                        """
            send_mail(recipients, subject, message)

            # redirect back to confirmation
            return render_template("passwordrecoverysent.html")
        elif formAction == "returnHome":
            return redirect("/login")
        else:
            return apology("Misc Error")


@app.route("/validatepwchange", methods=["GET", "POST"])
def validatePWchange():
    code_timeout_limit = 2#minutes
    if session.get("user_uuid") is not None:
        flash("Already logged in...")
        return redirect("/")
    if request.method == "GET":
        new_email = request.args.get("email")
        error = request.args.get("error")
        if new_email == "":
            return apology("not found","404")
        new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
        if len(new_user) != 1:
            return apology("No user found")
        elif new_user[0]['validateemail'] == "":
            flash("Email already validated")
            return redirect("/")
        #get the user's autorization code:
        fullcodedetails = new_user[0]['validateemail'].split(";")
        valid_code = fullcodedetails[1]
        start_timestamp = datetime.datetime.strptime(fullcodedetails[2], '%Y-%m-%d %H:%M:%S.%f')
        validate_timestamp = datetime.datetime.now()
        time_dif = validate_timestamp - start_timestamp
        time_dif_minutes = time_dif.total_seconds() / 60
        if time_dif_minutes > code_timeout_limit:
            # authorization code expired, new authcode and send email
            authcode = generate_new_authcode(new_email)
            error = "timeout"
            return redirect(f"/validateemail?email={new_email}&error={error}")

        # If the authcode was sent with the url (GET), this would be the case if the user clicks the email link
        authcode = request.args.get("authcode")
        if authcode != None:
            authcode = authcode.upper()
            if authcode == valid_code:
                # accound validated
                db.execute("UPDATE users SET validateemail = '' WHERE uuid = :uuid", uuid=new_user[0]['uuid'])
                session["user_uuid"] = new_user[0]["uuid"]
                session["firstname"] = new_user[0]["firstname"]
                session["neighborhood_check"] = "0"
                logHistory("other", "email_validated", "", "", "", "")
                # redirect back to the index (root) page
                flash(new_user[0]["firstname"] + ", your email has been validated.")
                return redirect("/")
            else:
                error = "incorrect"
                return redirect(f"/validateemail?email={new_email}&error={error}")

        errormessage = ""
        error = request.args.get("error")
        if error != None:
            if error == "":
                errormessage = ""
            elif error == "timeout":
                errormessage = "Your prior code has expired, please check your email for a new one."
            elif error == "incorrect":
                errormessage = "Incorrect authorization code. Please try again."
        return render_template("validateemail.html", new_email=new_email, errormessage=errormessage)
    else:#POST
        formAction = request.form.get("returnedAction")
        new_email = request.form.get("useremail")
        if formAction == "resendCode":
            new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
            if len(new_user) != 1:
                return apology("Error: No user found")
            elif new_user[0]['validateemail'] == "":
                flash("Email already validated")
                return redirect("/")
            # resend new user confirmation
            # get a new authcode (and set it in the db and send email)
            authcode = generate_new_authcode(new_email)
            flash("New authorization code has been emailed.")
            return redirect(f"/validateemail?email={new_email}")
        elif formAction == "confirmAccount":
            # get the form data
            input_authcode = request.form.get("authcode").upper()
            new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
            if len(new_user) != 1:
                return apology("Error: No user found")
            elif new_user[0]['validateemail'] == "":
                flash("Email already validated")
                return redirect("/")
            #get the user's autorization code:
            fullcodedetails = new_user[0]['validateemail'].split(";")
            valid_code = fullcodedetails[1]
            start_timestamp = datetime.datetime.strptime(fullcodedetails[2], '%Y-%m-%d %H:%M:%S.%f')
            validate_timestamp = datetime.datetime.now()
            time_dif = validate_timestamp - start_timestamp
            time_dif_minutes = time_dif.total_seconds() / 60
            if time_dif_minutes > code_timeout_limit:
                # authorization code expired, new authcode and send email
                authcode = generate_new_authcode(new_email)

                errormessage = "Your prior code has expired, please check your email for a new one."
                return render_template("validateemail.html", new_email=new_email, errormessage=errormessage)
            if input_authcode == valid_code:
                # accound validated
                send_email_welcome(new_email, new_user[0]["firstname"])
                db.execute("UPDATE users SET validateemail = '' WHERE uuid = :uuid", uuid=new_user[0]['uuid'])
                session["user_uuid"] = new_user[0]["uuid"]
                session["firstname"] = new_user[0]["firstname"]
                session["neighborhood_check"] = "0"
                logHistory("other", "email_validated", "", "", "", "")
                # redirect back to the index (root) page
                flash(new_user[0]["firstname"] + ", your email has been validated.")
                return redirect("/")
            else:
                error = "incorrect"
                return redirect(f"/validateemail?email={new_email}&error={error}")

        else:
            return apology("Misc Error")


@app.route("/ContactUs", methods=["GET", "POST"])
@login_required
def contactus():
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    user_details = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=userUUID)[0]
    email = user_details['email']
    username = user_details['username']

    if request.method == "GET":
        return render_template("ContactUs.html", openActions=countActions(), firstname=firstname, email=email, username=username)
    else: #post
        formAction = request.form.get("returnedAction")
        if formAction == "cancel":
            return redirect("/manageaccount")
        elif formAction == "sendMe":
            message = request.form.get("messsage")
            shareList = request.form.get("shareList")
            if message == "":
                flash("You must include something in the message box.")
                return render_template("ContactUs.html", openActions=countActions(), firstname=firstname, email=email, username=username)
            email = "No email shared"
            username = "No username shared"
            firstname = "Anonymous"
            if shareList != "":
                share_items = shareList.split(",")
                for item in share_items:
                    itemname = item.split("_")[0]
                    if itemname == "email":
                        email = user_details['email']
                    elif itemname == "firstname":
                        firstname = user_details['firstname']
                    elif itemname == "username":
                        username == user_details['username']
                    else:
                        firstname = "CONTACT FORM SUBMISSION PARSE ERROR"
            full_message = "\n" + firstname + " has submitted a 'contact us' email from " + email + "\n" + "Username: " + username + "\n" + " ----- message follows ----- \n\n" + message + "\n\n ----- end message -----"
            #print(full_message)
            send_mail([app.config['MAIL_USERNAME']], "ContactUs_Submission", full_message)
            #log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "feedback_email", "", "", "", "")
            flash("Your message has been sent, thank you!")
            return redirect("/manageaccount")
        else:
            return apology("Misc error")


@app.route("/TermsAndConditions")
def termsandconditions():
    if session.get("user_uuid") is None:
        firstname = ""
        openActions = 0
    else:
        firstname = session.get("firstname")
        openActions = countActions()
    return render_template("TermsAndConditions.html", openActions=openActions, firstname=firstname)


@app.route("/PrivacyPolicy")
def privacypolicy():
    if session.get("user_uuid") is None:
        firstname = ""
        openActions = 0
    else:
        firstname = session.get("firstname")
        openActions = countActions()
    return render_template("PrivacyPolicy.html", openActions=openActions, firstname=firstname)




################################################################
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
# |    [6]   misc other helper functions...                  | #
# ~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~--~-- #
################################################################

def format_tools(databasepull):
    formattedtools = {}
    for tool in databasepull:
        owner = "someoneelse"
        if tool["owneruuid"] == session.get("user_uuid"):
            owner = "mine"
        if tool["category"] == "hand":
            category = "æ"
        elif tool["category"] == "power":
            category = "‰"
        elif tool["category"] == "garden":
            category = "»"
        elif tool["category"] == "fastening":
            category = "Þ"
        else:
            category = "‡"
        if tool["photo"] == "none":
            photo = ""
        else:
            photo = get_image_s3(tool["toolid"] + "_thumb.png")
        info = {'toolname': tool["toolname"], 'toolid': tool["toolid"], 'state': tool["state"], 'category': category, 'private': tool["private"], 'photo': photo, 'owner': owner}
        formattedtools[tool["toolid"]] = info
    '''Tool Category Symobls:
         Hand: æ
         Power: ‰
         Garden: »
         Fastening: Þ
         Uncategorized: ‡    '''
    return formattedtools


def countActions():
    # use this to populate openActions
    userUUID = session.get("user_uuid")
    myActionCount_db = db.execute("SELECT DISTINCT actionid FROM actions WHERE targetuuid = :userUUID AND state = 'open' AND type = 'toolrequest' AND deleted = 0;", userUUID=userUUID)
    myActionCount  = len(myActionCount_db)
    if myActionCount == 0:
        myActionCount = ""
    return myActionCount


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


#log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
def logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment):
    userUUID = session.get("user_uuid")
    db.execute("INSERT INTO history (type, action, useruuid, seconduuid, toolid, neighborhoodid, comment, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", historyType, action, userUUID, seconduuid, toolid, neighborhoodid, comment, datetime.datetime.now())


# Build the description text based on the action and names
def getDescriptionTool(action, user1, user2, comment):
    finaltext = ""
    if action == "borrow":
        finaltext = user2 + " borrowed it from " + user1
    elif action == "request":
        finaltext = user1 + " requested it from " + user2
    elif action == "approve":
        finaltext = user1 + " approved the request"
    elif action == "reject":
        finaltext = user1 + " rejected the request"
    elif action == "return":
        finaltext = user1 + " returned it"
    elif action == "cancel":
        finaltext = user1 + " cancelled the request"
    elif action == "edittool":
        finaltext = comment
    elif action == "createtool":
        finaltext = "Tool created"
    elif action == "requirereturn":
        finaltext = user1 + " required " + user2 + " to return it."
    elif action == "deletetool":
        finaltext = "Tool deleted"
    else:
        finaltext = " -- ERROR -- "

    return finaltext


# Build the description text based on the action and names
def getDescriptionNBH(action, user1, user2, comment):
    finaltext = ""
    if action == "join":
        finaltext = user1 + " joined"
    elif action == "left":
        finaltext = user1 + " left"
    elif action == "createneighborhood":
        finaltext = "Neighborhood created"
    elif action == "editneighborhood":
        finaltext = comment
    elif action == "deleteneighborhood":
        finaltext = "Neighborhood deleted"
    elif action == "edittool":
        finaltext = "You changed the tool visibilities for this NBH"
    else:
        finaltext = " -- ERROR -- "

    return finaltext


# Create local thumbnail
def save_local_thumbnail(image_uuid):
    file_thumb = UPLOAD_FOLDER + image_uuid + "_thumb.png"
    if os.path.exists(file_thumb):
        os.remove(file_thumb)
    MAX_SIZE = (75, 75)
    image = Image.open(UPLOAD_FOLDER + image_uuid + ".jpeg")
    image.thumbnail(MAX_SIZE, Image.ANTIALIAS)
    image.save(file_thumb)
    print("thumbnail created.")


# AWS S3 Storage functions
def delete_images_s3(image_uuid):
    key_name = image_uuid + ".jpeg"
    try:
        s3.delete_object(
            Bucket=app.config["S3_BUCKET"],
            Key=key_name
        )
    except Exception as e:
        print("Something Happened - FullFileDelete: ", e)
    key_name = image_uuid + "_thumb.png"
    try:
        s3.delete_object(
            Bucket=app.config["S3_BUCKET"],
            Key=key_name
        )
    except Exception as e:
        print("Something Happened - ThumbnailDelete: ", e)

def images_to_s3(image_uuid):
    # Upload image and thumbnail to AWS
    #delete images if they are stored on S3
    delete_images_s3(image_uuid)
    # upload to aws s3
    file_name = UPLOAD_FOLDER + image_uuid + ".jpeg"#full source filepath
    key_name = image_uuid + ".jpeg"#just the file name
    s3.upload_file(file_name, app.config["S3_BUCKET"], key_name, ExtraArgs={
        "ACL": "public-read",
        "ContentType": "image/jpeg"
    })

    file_name = UPLOAD_FOLDER + image_uuid + "_thumb.png"
    key_name = image_uuid + "_thumb.png"
    s3.upload_file(file_name, app.config["S3_BUCKET"], key_name, ExtraArgs={
        "ACL": "public-read",
        "ContentType": "image/png"
    })


def get_image_s3(image_uuid_with_ext, expire_in=3600):
    # just send the full asw filepath for now
    #return "{}{}".format(app.config["S3_LOCATION"], image_uuid_with_ext)  <--- delete this...
    # returns the presigned url for the full-sized image
    try:
        response = s3.generate_presigned_url('get_object',
                                                    Params={'Bucket': app.config["S3_BUCKET"],
                                                            'Key': image_uuid_with_ext},
                                                    ExpiresIn=expire_in)#seconds
    except ClientError as e:
        logging.error(e)
        print("Something Happened - ImageFetchFail: ", e)
        return None

    # The response contains the presigned URL
    return response


# generic send_mail([recipients], subject, message):
def send_mail(recipients, subject, message):
    msg = Message(subject, sender = "sharetools.tk@gmail.com", recipients = recipients)
    msg.body = message
    msg.html = message.replace("\n","<br />\n")
    mail.send(msg)
    print("Mail Sent")


def send_email_auth(email, authcode):
    # Send welcome email
    # generic send_mail([recipients], subject, message)
    recipients = [email]
    subject = "Welcome to ToolShare!"
    message = f"""\
                <html style="font-family: arial; background-color: lightgray;">
                  <head>
                    <title>Tool Share - Validate Email</title>
                  </head>

                  <body style="margin: 0; background-color: white; border: 7px solid lightgray; position: absolute; top: 0; left: 0;">
                    <div style="width: 100%; background-color: #f8f9fa;">
                      <a href="https://sharetools.tk"><img src="https://i.imgur.com/dzuJftm.png" alt=""></a>
                    </div>
                    <div style="padding: 20px 10px 30px 10px; background-color: white; ">
                      Please confirm this is a functional email by entering this one-time
                      confirmation code back in the app or by simply clicking the link.<br>
                      <span style="font-size: small;">(the code and link are only valid for 2 minutes)</span>
                      <div style="padding: 25px;">
                        <span style="border: 2px dashed gray; border-radius: 8px; padding: 4px 3px 6px 7px; width: fit-content; color:#cc5500; font-size: 1.3em; font-weight: bold;">
                          {authcode}
                        </span>
                        <span style="padding-left: 12px;">
                          or click this <a href="https://sharetools.tk/validateemail?email={email}&authcode={authcode}"> direct link</a>.
                        </span>
                      </div>

                      <div style="font-size: small; padding-top: 20px"><i>#dontbeafoolborrowatool</i></div>
                    </div>
                    <div style="padding: 8px; position: fixed; bottom: 0; left: 0; width: 100%;">
                      <div style="font-size: 10px; color: gray; text-align: center; width: 100%;">
                        Copyright 2021 / Steven Small / All Rights Reserved
                      </div>
                    </div>
                  </body>
                </html>
                """
    # Send welcome email with the proper authorization code
    send_mail(recipients, subject, message)


def send_email_welcome(email, firstname):
    # Send welcome email
    # generic send_mail([recipients], subject, message)
    recipients = [email]
    subject = "Welcome to ToolShare!"
    message = f"""\
                <html style="font-family: arial; background-color: lightgray;">
                  <head>
                    <title>Tool Share - Welcome</title>
                  </head>

                  <body style="margin: 0; background-color: white; border: 7px solid lightgray; position: absolute; top: 0; left: 0;">
                    <div style="width: 100%; background-color: #f8f9fa;">
                      <a href="https://sharetools.tk"><img src="https://i.imgur.com/dzuJftm.png" alt=""></a>
                    </div>
                    <div style="padding: 20px 10px 30px 10px; background-color: white; ">
                      <h4>{firstname}, welcome to Tool Share!</h4>
                      <p>
                        Your email address has been confirmed, and your account has been created. You can go ahead and add
                        any tools that you like to your personal toolbox.<br>
                        In order to find tools to borrow though, you must first join a neighborhood. It's also super easy to create
                        a new neighborhood and share the link with your friends.
                      </p>
                      <p>
                        We hope you enjoy this app and that it helps you save money, reduce
                        consumption, and reduce waste.
                      </p>

                      Thanks, and welcome aboard!

                      <div style="font-size: small; padding-top: 20px"><i>#dontbeafoolborrowatool</i></div>
                    </div>
                    <div style="padding: 8px; position: fixed; bottom: 0; left: 0; width: 100%;">
                      <div style="font-size: 10px; color: gray; text-align: center; width: 100%;">
                        Copyright 2021 / Steven Small / All Rights Reserved
                      </div>
                    </div>
                  </body>
                </html>
                """
    # Send welcome email with the proper authorization code
    send_mail(recipients, subject, message)


def send_email_toolaction(toolid, othername, actionmsg):
    #get the Info
    tooldeetz = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]
    toolowner = db.execute("SELECT * FROM users WHERE uuid = :uuid", uuid=tooldeetz['owneruuid'])[0]
    if tooldeetz['photo'] == "none":
        photo = "https://i.imgur.com/oXNuzWq.png"
    else:
        photo = get_image_s3(str(tooldeetz['toolid']) + ".jpeg", 864000)
    toolname = tooldeetz['toolname'].lower()
    toolownername = toolowner['firstname']
    #send the email
    recipients = [toolowner['email']]
    subject = "ToolShare: You have an action."
    message = f"""\
                <html style="font-family: arial; background-color: lightgray;">
                  <head>
                    <title>Tool Share - New Action</title>
                  </head>

                  <body style="margin: 0; background-color: white; border: 7px solid lightgray; position: absolute; top: 0; left: 0;">
                    <div style="width: 100%; background-color: #f8f9fa;">
                      <a href="https://sharetools.tk" alt=""></a>
                    </div>
                    <div style="padding: 20px 10px 30px 10px; background-color: white; ">
                      <h4>{toolownername}, you have a new action on Tool Share!</h4>
                      <div style="">
                        <img style="width: 180px; height: 180px; border-radius: 15px;" src='{photo}' alt="no photo"><br>
                      </div>
                      <p>
                        Your tool, <strong>{toolname}</strong> has been {actionmsg} by {othername}.
                      </p>
                      <p>
                        Have a look at the details or approve/reject <a href="https://sharetools.tk/actions">here</a>!<br>
                        <span style="font-size: small;">You can also check out your <a href="https://sharetools.tk/history">history</a> too.</span>
                      </p>

                      <div style="font-size: small; padding-top: 20px"><i>#dontbeafoolborrowatool</i></div>
                    </div>
                    <div style="padding: 8px; position: fixed; bottom: 0; left: 0; width: 100%;">
                      <div style="font-size: 10px; color: gray; text-align: center; width: 100%;">
                        Copyright 2021 / Steven Small / All Rights Reserved
                      </div>
                    </div>
                  </body>
                </html>
                """
    # Send welcome email with the proper authorization code
    send_mail(recipients, subject, message)


def generate_new_authcode(email):
    authcode = str(uuid.uuid4().hex)[:6].upper()
    time_now = str(datetime.datetime.now())
    authcode_withtime = "Unregistered_Email" + ";" + authcode + ";" + time_now
    db.execute("UPDATE users SET validateemail = :authcode WHERE email = :email", authcode=authcode_withtime, email=email)
    send_email_auth(email, authcode)
    return authcode


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
