
#imports
import datetime
import uuid
import os
from flask import Blueprint, session, redirect, url_for, render_template, request, flash
from flask import current_app as app

from sub_modules.helpers import login_required, neighborhood_required, format_tools, countActions, logHistory, apology, getDescriptionTool, get_user_communications
from sub_modules.image_mgmt import get_image_s3, images_to_s3, save_local_thumbnail, delete_images_s3
from sub_modules.emails import requestApproved, requestDenied, send_email_toolaction


#setup the blueprint for this section of the app
tools_and_actions_bp = Blueprint('tools_and_actions_bp', __name__)
#use as needed:   db = app.config["database_object"]




@tools_and_actions_bp.route("/")
def index():
    #Join - landing page if not logged in, if logged in redirect to the 'home'
    if session.get("user_uuid") is not None:
        return redirect(url_for("tools_and_actions_bp.tools"))
    return render_template("general/index.html")


@tools_and_actions_bp.route("/tools")
@login_required
def tools():
    db = app.config["database_object"]
    """Show tool management page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    # get all user tools
    mytoollist = db.execute("SELECT * FROM tools WHERE owneruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL
    if len(mytoollist) == 0:
        mytools = ['no-tools']
    else:
        mytools = format_tools(mytoollist)

    #check if the user is part of a neighborhood
    if session.get("neighborhood_check") == "0":
        borrowedtools = ['no-nbh']
    else:
        # get all of the tools that the user has borrowed
        borrowedlist = db.execute("SELECT * FROM tools WHERE activeuseruuid = :userUUID AND deleted = 0 ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL
        borrowedtools = format_tools(borrowedlist)
    
    # render the template
    return render_template("tools/tools.html", setActive1="active", openActions=countActions(), firstname=firstname, mytools=mytools, borrowedtools=borrowedtools)


@tools_and_actions_bp.route('/myTools')
@login_required
def my_redirect1():
    return redirect(url_for('tools_and_actions_bp.tools') + '#myTools')


@tools_and_actions_bp.route('/borrowed')
@login_required
def my_redirect2():
    return redirect(url_for('tools_and_actions_bp.tools') + '#borrowed')


@tools_and_actions_bp.route("/actions", methods=["GET", "POST"])
@login_required
def actions():
    db = app.config["database_object"]
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
            commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A AND banned = 0 INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B AND banned = 0);", A=userUUID, B=item['originuuid'])
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
            commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A AND banned = 0 INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B AND banned = 0);", A=userUUID, B=tooldetails['owneruuid'])
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
        return render_template("tools/actions.html", setActive2="active", openActions=countActions(), firstname=firstname, myrequests=myrequests, myapprovals=myapprovals)
    else: #POST
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
                # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
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
                requestApproved(returnedActionID, approveReject_comments)
            else: # the request was rejected
                requestDenied(returnedActionID, approveReject_comments)
        return ('', 204)


@tools_and_actions_bp.route("/findtool", methods=["GET", "POST"])
@login_required
@neighborhood_required
def findtool():
    db = app.config["database_object"]
    '''Find a tool from all users' neighborhoods'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        # get all of the tools the user could borrow from their neighborhoods
        #alltoollist = db.execute("SELECT * FROM tools WHERE owneruuid IN (SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID)) AND private = 0 AND deleted = 0  ORDER BY toolname COLLATE NOCASE;", userUUID=userUUID)
        alltoollist = db.execute("SELECT * FROM tools WHERE toolid IN (SELECT DISTINCT toolid FROM toolvisibility WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0)) ORDER BY toolname;", userUUID=userUUID)#removed ' COLLATE NOCASE' for postgreSQL
        #SELECT DISTINCT toolid FROM toolvisibility WHERE neighborhoodid IN (10, 13);
        alltools = format_tools(alltoollist)

        # render the template
        return render_template("tools/findtool.html", openActions=countActions(), firstname=firstname, alltools=alltools)
    else:
        # get data from the form
        flash("do nothing???")
        return redirect(url_for('tools_and_actions_bp.tools') + '#borrowed')


@tools_and_actions_bp.route("/newtool", methods=["GET", "POST"])
@login_required
def newtool():
    db = app.config["database_object"]

    '''Create a new tool'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")

    myNeighborhoodsData = db.execute("SELECT neighborhoodid, neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0);", userUUID=userUUID)
    myNeighborhoods = {}
    for i in range(len(myNeighborhoodsData)):
        info = {'neighborhoodID': myNeighborhoodsData[i]['neighborhoodid'],
                'neighborhoodName': myNeighborhoodsData[i]['neighborhood']}
        myNeighborhoods[myNeighborhoodsData[i]['neighborhoodid']] = info

    if request.method == "GET":
        return render_template("tools/newtool.html", openActions=countActions(), firstname=firstname, myNeighborhoods=myNeighborhoods)

    else: # Post
        # get data from the form
        toolname = request.form.get("toolname")
        if toolname == "":
            flash("Tool entry error: please provide a tool name.")
            return render_template("tools/newtool.html", openActions=countActions(), firstname=firstname, myNeighborhoods=myNeighborhoods)

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

        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("tool", "createtool", "", new_tool_uuid, "", "")

        flash("Successfully added the tool")
        return redirect(url_for('tools_and_actions_bp.tools') + '#myTools')


@tools_and_actions_bp.route("/tool_details", methods=["GET", "POST"])
#@login_required  #allow not logged in for new users to see tool preview
def tool_details():
    db = app.config["database_object"]
    SEND_EMAIL_ACTIONS = app.config["SEND_EMAIL_ACTIONS"]
    #if not logged in, this is an external invite for a potential new user (toolwelcome)
    # They will be redirected to a welcome page and be offered to join or login
    if session.get("user_uuid") is None:
        toolid = request.args.get("toolid")
        if not toolid:
            return redirect("/")
        else:
            tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)
            if len(tooldetails) == 0:
                return apology("No tool")
            tooldetails = tooldetails[0]
            if tooldetails["private"] == 1:
                return apology("tool is private", "sorry")
            toolname = tooldetails["toolname"]
            if tooldetails["features"]:
                description = tooldetails["features"].split('\n')
            else:
                description = ""
            photo = ""
            if tooldetails["photo"] != 'none':
                photo = get_image_s3(toolid + ".jpeg")
            return render_template("tools/toolwelcome.html", toolname=toolname, toolid=toolid, description=description, photo=photo)

    #else:
    '''Show user tool details page'''
    if request.method == "GET":
        userUUID = session.get("user_uuid")
        firstname = session.get("firstname")
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
        sharedneighborhoods = db.execute("SELECT neighborhoodid FROM memberships WHERE useruuid = :ownerUUID AND banned = 0 INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0;", ownerUUID=ownerUUID, userUUID=userUUID)
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
            commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A AND banned = 0 INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B AND banned = 0);", A=userUUID, B=ownerUUID)
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

        activeuseremail = ""
        activeuserphonenumber = ""
        activeuseryescall = ""
        activeuseryessms = ""

        if state != 'available':
            activeuserdetails = db.execute("SELECT * FROM users WHERE uuid = :activeuser;", activeuser=tooldetails["activeuseruuid"])[0]
            activeuserfirstname = activeuserdetails['firstname']
            activeuserusername = activeuserdetails['username']
            activeuseruuid = tooldetails["activeuseruuid"]
            if activeuseruuid == ownerUUID:
                commonneighborhoods = "(hey, that's you!)"
            else:
                commonneighborhoods_data = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :A AND banned = 0 INTERSECT SELECT neighborhoodid FROM memberships WHERE useruuid = :B AND banned = 0);", A=activeuseruuid, B=ownerUUID)
                commonneighborhoods = []
                for i in commonneighborhoods_data:
                    commonneighborhoods.append(i['neighborhood'])

            # additional communication preference settings
            [activeuseremail, activeuserphonenumber, activeuseryescall, activeuseryessms] = get_user_communications(activeuseruuid)

        if tooldetails["activeuseruuid"] == userUUID:
            userborrowed = True
        else:
            userborrowed = False

        photo = ""
        if tooldetails["photo"] != 'none':
            photo = get_image_s3(toolid + ".jpeg")

        # additional communication preference settings
        [owneremail, ownerphonenumber, owneryescall, owneryessms] = get_user_communications(ownerdetails['uuid'])

        return render_template("tools/tooldetails.html",
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
                                toolhistory=toolhistory,
                                owneremail=owneremail,
                                ownerphonenumber=ownerphonenumber,
                                owneryescall=owneryescall,
                                owneryessms=owneryessms,
                                activeuseremail=activeuseremail,
                                activeuserphonenumber=activeuserphonenumber,
                                activeuseryescall=activeuseryescall,
                                activeuseryessms=activeuseryessms)
    else:#Post
        userUUID = session.get("user_uuid")
        firstname = session.get("firstname")
        formAction = request.form.get("returnedAction")
        toolid = request.form.get("toolid")
        if formAction == "returnHome":
            return redirect(url_for('tools_and_actions_bp.tools') + '#myTools')
        elif formAction == "requestBorrow":
            requestComment_raw = request.form.get("requestComment")
            if requestComment_raw == "":
                requestComment = ""
            else:
                requestComment = firstname + ': "' + requestComment_raw + '"'
            toolownerUUID = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["owneruuid"]
            db.execute("INSERT INTO actions (type, originuuid, targetuuid, toolid, messages, timestamp_open) VALUES (?, ?, ?, ?, ?, ?);", "toolrequest", userUUID, toolownerUUID, toolid, requestComment, datetime.datetime.now())
            db.execute("UPDATE tools SET state = 'requested', activeuseruuid = :userUUID WHERE toolid = :toolid;", toolid=toolid, userUUID=userUUID)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "request", toolownerUUID, toolid, "", request.form.get("requestComment"))
            if SEND_EMAIL_ACTIONS == 1:
                # notify the tool owner via email
                recipientuuid = toolownerUUID
                subject = "Tool Share - you have a tool request"
                toolname = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["toolname"]
                actionmsg = f"{firstname} has requested to borrow your tool: <strong>{toolname}</strong>."
                secondline = "<p>Have a look at the details and approve or reject <a href='https://sharetools.tk/actions'>here</a>!</p>"
                send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline)

            flash('Tool Requested')
            return redirect(url_for('tools_and_actions_bp.tools') + '#borrowed')
        elif formAction == "markBorrowed":
            db.execute("INSERT INTO actions (type, state, originuuid, targetuuid, toolid, messages, timestamp_open, timestamp_close) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", "toolrequest", "dismissed", userUUID, userUUID, toolid, "self borrow", datetime.datetime.now(), datetime.datetime.now())
            db.execute("UPDATE tools SET state = 'borrowed', activeuseruuid = :userUUID WHERE toolid = :toolid;", toolid=toolid, userUUID=userUUID)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "borrow", "", toolid, "", "self-borrowed")
            flash('Tool marked as Borrowed')
            return redirect(url_for('tools_and_actions_bp.tools') + '#borrowed')
        elif formAction == "returnTool":
            toolownerUUID = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["owneruuid"]
            if userUUID == toolownerUUID:
                message = "self return"
                state = "dismissed"
                seconduuid = ""
            else:
                if SEND_EMAIL_ACTIONS == 1:
                    # notify the tool owner via email
                    recipientuuid = toolownerUUID
                    subject = "Tool Share - you have a tool returning"
                    toolname = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["toolname"]
                    actionmsg = f"{firstname} has returned your tool: <strong>{toolname}</strong>."
                    secondline = "<p>Make sure you connect with them to get the tool back.<br> Thanks for sharing!</p>"
                    send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline)

                message = firstname + " returned the tool."
                state = "closed"
                seconduuid = toolownerUUID
            db.execute("INSERT INTO actions (type, state, originuuid, targetuuid, toolid, messages, timestamp_open, timestamp_close) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", "toolrequest", state, userUUID, userUUID, toolid, message, datetime.datetime.now(), datetime.datetime.now())
            db.execute("UPDATE tools SET state = 'available', activeuseruuid = NUlL WHERE toolid = :toolid;", toolid=toolid)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "return", seconduuid, toolid, "", message)
            flash('Tool returned')
            return redirect(url_for('tools_and_actions_bp.tools') + '#borrowed')
        elif formAction == "cancelRequest":
            actionid = db.execute("SELECT actionid FROM actions WHERE toolid = :toolid AND state = 'open' AND originuuid = :userUUID;", toolid=toolid, userUUID=userUUID)[0]['actionid']
            db.execute("UPDATE actions SET state = 'dismissed', timestamp_close = :timeclose WHERE actionid = :actionid;", timeclose=datetime.datetime.now(), actionid=actionid)
            db.execute("UPDATE tools SET state = 'available', activeuseruuid = NUlL WHERE toolid = :toolid;", toolid=toolid)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            toolownerUUID = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["owneruuid"]
            logHistory("tool", "cancel", toolownerUUID, toolid, "", "")
            flash('Cancelled the tool request')
            return redirect(url_for('tools_and_actions_bp.tools') + '#borrowed')
        elif formAction == "approveRequest":
            actiondetails = db.execute("SELECT * FROM actions WHERE toolid = :toolid AND type = 'toolrequest' AND state = 'open' AND targetuuid = :userUUID;", toolid=toolid, userUUID=userUUID)[0]
            actionid = actiondetails['actionid']
            requestApproved(actionid, "")
            flash('Tool request approved')
            return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)
        elif formAction == "denyRequest":
            actiondetails = db.execute("SELECT * FROM actions WHERE toolid = :toolid AND type = 'toolrequest' AND state = 'open' AND targetuuid = :userUUID;", toolid=toolid, userUUID=userUUID)[0]
            actionid = actiondetails['actionid']
            requestDenied(actionid, "")
            flash('Tool request denied')
            return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)
        elif formAction == "requireReturn":
            # get the useruuid for who has the tool "activeuseruuid" of the tool
            activeuseruuid = db.execute("SELECT activeuseruuid FROM tools WHERE toolid = :toolid;", toolid=toolid)[0]['activeuseruuid']
            # create new return tool action ("requirereturn")
            db.execute("INSERT INTO actions (type, originuuid, targetuuid, toolid, messages, timestamp_open) VALUES (?, ?, ?, ?, ?, ?);", "requirereturn", userUUID, activeuseruuid, toolid, "The tool owner has requested their tool back", datetime.datetime.now())
            # change state of the tool to 'overdue'
            db.execute("UPDATE tools SET state = 'overdue' WHERE toolid = :toolid;", toolid=toolid)
            if SEND_EMAIL_ACTIONS == 1:
                # notify the tool owner via email
                borrower = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["activeuseruuid"]
                recipientuuid = borrower
                subject = "Tool Share - please return a tool"
                toolname = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]["toolname"]
                actionmsg = f"{firstname} has required that you return their tool: <strong>{toolname}</strong>."
                secondline = "<p>Please get the tool back to them and remember to mark the tool as <a href='https://sharetools.tk/tool_details?toolid={toolid}'>returned</a>.</p>"
                send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline)

            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "requirereturn", activeuseruuid, toolid, "", "")
            flash('Tool return requested')
            return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)
        elif formAction == "edit":
            return redirect(url_for('tools_and_actions_bp.edittool') + '?toolid=' + toolid)
        elif formAction == "makePublic":
            db.execute("UPDATE tools SET private = '0' WHERE toolid = :toolid;", toolid=toolid)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "edittool", "", toolid, "", "Tool marked public.")
            flash('Tool marked as public')
            return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)
        elif formAction == "makePrivate":
            db.execute("UPDATE tools SET private = '1' WHERE toolid = :toolid;", toolid=toolid)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "edittool", "", toolid, "", "Tool marked private.")
            flash('Tool marked as private')
            return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)
        elif formAction == "deleteTool":
            db.execute("UPDATE tools SET deleted = '1', photo = 'none' WHERE toolid = :toolid;", toolid=toolid)
            db.execute("DELETE FROM toolvisibility WHERE toolid = :toolid;", toolid=toolid)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("tool", "deletetool", "", toolid, "", "")
            flash('Tool deleted')
            return redirect(url_for('tools_and_actions_bp.tools') + '#myTools')
        else:
            return apology("Misc error")


@tools_and_actions_bp.route("/edittool", methods=["GET", "POST"])
@login_required
def edittool():
    db = app.config["database_object"]
    UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']

    '''Show user edit tool page'''
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


        myNeighborhoodsData = db.execute("SELECT neighborhoodid, neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0);", userUUID=userUUID)

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

        return render_template("tools/edittool.html", openActions=countActions(), firstname=firstname, toolname=toolname, publicCheck=publicCheck, description=description, category=category, health=health, photo=photo, toolid=toolid, notes=notes, myNeighborhoods=myNeighborhoods, toolVis=toolVis)
    else:#post
        toolid = request.form.get("toolid")
        toolname = request.form.get("toolname")
        if toolname == "":
            flash("Tool entry error: please provide a tool name.\nNo changes made to the tool.")
            return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)
        category = request.form.get("category")
        health = request.form.get("health")
        features = request.form.get("features")
        notes = request.form.get("notes")

        myNeighborhoodsData = db.execute("SELECT neighborhoodid, neighborhood FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0);", userUUID=userUUID)
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
            delete_images_s3(toolid)

            toolimage = "none"
            db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, photo = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, toolimage, health, features, notes, toolid)
        else: #photostate was "unchanged"
            db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, health, features, notes, toolid)


        # update the database details for the given toolid
        #db.execute("UPDATE tools SET toolname = ?, private = ?, category = ?, photo = ?, health = ?, features = ?, notes = ? WHERE toolid = ?;", toolname, private, category, toolimage, health, features, notes, toolid)

        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("tool", "edittool", "", toolid, "", "full edit")
        flash("Successfully updated the tool")
        return redirect(url_for('tools_and_actions_bp.tool_details') + '?toolid=' + toolid)

