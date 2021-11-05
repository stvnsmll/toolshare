# helper function module (functions that don't fit anywhere else)

#imports
#import requests
#import urllib.request
import datetime

from flask import flash, redirect, render_template, request, session, url_for
from flask import current_app as app
from functools import wraps

from .image_mgmt import get_image_s3




def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("general/apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_uuid") is None:
            return redirect(url_for("users_bp.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def neighborhood_required(f):
    """
    Decorate routes to require to join a neighborhood.

    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("neighborhood_check") == "0":
            flash("Please join a neighborhood.")
            return redirect("/neighborhoods#join")
        return f(*args, **kwargs)
    return decorated_function


def logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment):
    # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
    db = app.config["database_object"]
    userUUID = session.get("user_uuid")
    db.execute("INSERT INTO history (type, action, useruuid, seconduuid, toolid, neighborhoodid, comment, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", historyType, action, userUUID, seconduuid, toolid, neighborhoodid, comment, datetime.datetime.now())


def countActions():
    # use this to populate openActions
    db = app.config["database_object"]
    userUUID = session.get("user_uuid")
    myActionCount_db = db.execute("SELECT DISTINCT actionid FROM actions WHERE targetuuid = :userUUID AND state = 'open' AND type = 'toolrequest' AND deleted = 0;", userUUID=userUUID)
    myActionCount  = len(myActionCount_db)
    if myActionCount == 0:
        myActionCount = ""
    return myActionCount 


def admin_check(userUUID, neighborhoodID):
    db = app.config["database_object"]
    # ensure that the provided user is an admin of the provided neighborhood                           |-- and admin = 1?
    admincheck = db.execute("SELECT * FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=userUUID, nbh=neighborhoodID)
    if len(admincheck) != 0:#confirm the user is at least a member
        if admincheck[0]['admin'] == 1:#the user is an admin
            return True
    return False


def member_check(userUUID, neighborhoodID):
    db = app.config["database_object"]
    # ensure that the provided user is a member of the provided neighborhood
    membercheck = db.execute("SELECT * FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh AND banned = 0;", uuid=userUUID, nbh=neighborhoodID)
    if len(membercheck) == 0:
        return False
    return True


def removeAllUserToolsFromNBH(userUUID, neighborhoodid):
    db = app.config["database_object"]
    # get all of the user's tools by toolID
    allmyToolsData = db.execute("SELECT toolid FROM tools WHERE owneruuid = :userUUID;", userUUID=userUUID)
    # for each tool, DB update to remove any associations with that neighborhood.
    for i in range(len(allmyToolsData)):
        db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :neighborhoodid AND toolid = :tool", neighborhoodid=neighborhoodid, tool=allmyToolsData[i]['toolid'])
    return 1


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


def getDescriptionTool(action, user1, user2, comment):
    # Build the description text based on the action and names
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


def getDescriptionNBH(action, user1, user2, comment):
    # Build the description text based on the action and names
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


def get_user_communications(uuid):
    db = app.config["database_object"]
    userdetails = db.execute("SELECT * FROM users WHERE uuid = :user;", user=uuid)
    if len(userdetails) == 0:
        #user does not exist
        return "error, no user"
    userdetails = userdetails[0]
    phonenumber = userdetails['phonenumber']
    email = userdetails['email']
    phonepref = userdetails['phonepref']#none/call/sms/both
    if phonepref == "both":
        yescall = True
        yessms = True
    elif phonepref == "call":
        yescall = True
        yessms = False
    elif phonepref == "sms":
        yescall = False
        yessms = True
    else:#phonepref == "none" (or some other error, just pass nothing)
        phonenumber = ""
        yescall = False
        yessms = False
    return [email, phonenumber, yescall, yessms]


