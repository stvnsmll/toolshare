
#imports
import uuid
from flask import session, request, flash, redirect, url_for, Blueprint, render_template
from werkzeug.security import check_password_hash, generate_password_hash
from flask import current_app as app

from sub_modules.helpers import login_required, neighborhood_required, apology, logHistory, countActions, admin_check, format_tools, removeAllUserToolsFromNBH


#setup the blueprint for this section of the app
neighborhoods_bp = Blueprint('neighborhoods_bp', __name__)
#use as needed:   db = app.config["database_object"]




@neighborhoods_bp.route("/neighborhoods", methods=["GET", "POST"])
@login_required
def neighborhoods():
    db = app.config["database_object"]

    """Show user's neighborhood page"""
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        mynbhlist = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0) AND deleted = 0;", userUUID=userUUID)
        myneighborhoods = {}
        for row in mynbhlist:
            info = {'neighborhood': row["neighborhood"], 'neighborhoodid': row["neighborhoodid"], 'zipcode': row["zip"]}
            myneighborhoods[row["neighborhoodid"]] = info

        allnbhlist = db.execute("SELECT * FROM neighborhoods WHERE private = '0' AND deleted = 0 AND neighborhoodid NOT IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0);", userUUID=userUUID)
        allneighborhoods = {}
        for row in allnbhlist:
            info = {'neighborhood': row["neighborhood"], 'neighborhoodid': row["neighborhoodid"], 'zipcode': row["zip"]}
            allneighborhoods[row["neighborhoodid"]] = info

        return render_template("neighborhood/neighborhoods.html", setActive3="active", openActions=countActions(), firstname=firstname, myneighborhoods=myneighborhoods, allneighborhoods=allneighborhoods)
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
        db.execute("INSERT INTO neighborhoods (neighborhoodid, neighborhood, zip, description, private, pwd) VALUES (?, ?, ?, ?, ?, ?, ?);", new_neighborhood_uuid, neighborhoodname, zipcode, description, private, password)
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

        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("neighborhood", "createneighborhood", "", "", new_neighborhood_uuid, "")

        flash("Successfully created the neighborhood.")
        return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')


@neighborhoods_bp.route("/neighborhood_details", methods=["GET", "POST"])
#@login_required #allow not logged in for new users to see neighborhood preview
def neighborhood_details():
    db = app.config["database_object"]

    if request.method == "GET":
        #if not logged in, this is an external invite for a potential new user
        # They will be redirected to a welcome page and be offered to join or login
        if session.get("user_uuid") is None:
            neighborhoodid = request.args.get("neighborhoodid")
            if not neighborhoodid:
                return redirect("/")
            else:
                neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]
                neighborhoodname = neighborhooddeetz["neighborhood"]
                if neighborhooddeetz["description"]:
                    description = neighborhooddeetz["description"].split('\n')
                else:
                    description = ""
                #Get some tool images to display to the prospective user
                sometoolslist = db.execute("SELECT * FROM tools WHERE toolid IN (SELECT DISTINCT toolid FROM toolvisibility WHERE neighborhoodid = :neighborhoodid) ORDER BY toolname;", neighborhoodid=neighborhoodid)
                if len(sometoolslist) > 4:
                    showtools = True
                    sometools = format_tools(sometoolslist[:5])#get the details on only the first 5 tools in this neighborhood
                else:
                    showtools = False
                    sometools = []
                return render_template("neighborhood/neighborhoodwelcome.html", neighborhoodname=neighborhoodname, neighborhoodid=neighborhoodid, description=description, showtools=showtools, sometools=sometools)

        #else:
        #user is already logged in
        """Show user neighborhood details page"""
        userUUID = session.get("user_uuid")
        firstname = session.get("firstname")

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
            if admin_check(userUUID, neighborhoodid):
                yesadmin = True
            else:
                yesadmin = False
            membercount_db = db.execute("SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid AND banned = 0;", neighborhoodid=neighborhoodid)
            membercount = len(membercount_db)
            membercheck = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid AND banned = 0;", userUUID=userUUID, neighborhoodid=neighborhoodid)
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
            return render_template("neighborhood/neighborhooddetails.html",
                                    openActions=countActions(),
                                    firstname=firstname,
                                    neighborhoodname=neighborhoodname,
                                    zipcode=zipcode,
                                    description=description,
                                    membercount=membercount,
                                    privateYN=privateYN,
                                    passwordYN=passwordYN,
                                    yesadmin=yesadmin,
                                    notmember=notmember,
                                    neighborhoodid=neighborhoodid,
                                    myTools=myTools)
    else:#POST
        userUUID = session.get("user_uuid")
        firstname = session.get("firstname")
        formAction = request.form.get("returnedAction")
        neighborhoodid = request.form.get("nbhid")
        if formAction == "join":
            # check if the ths user is banned from this neighborhood
            ban_check = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid AND banned = 1;", userUUID=userUUID, neighborhoodid=neighborhoodid)
            if len(ban_check) != 0:
                # the user is banned from this neighborhood
                return apology("Contact an admin for more information.", "Sorry, you are banned from this neighborhood")
            already_member_ckeck = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid AND banned = 0;", userUUID=userUUID, neighborhoodid=neighborhoodid)
            if len(already_member_ckeck) != 0:
                #already a member, cannot rejoin
                flash("Already a member of this neighborhood")
                return redirect(url_for('neighborhoods_bp.neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

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

            exists = db.execute("SELECT * FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh AND banned = 0;", uuid=userUUID, nbh=neighborhoodid)
            if len(exists) == 0:
                db.execute("INSERT INTO memberships (useruuid, neighborhoodid) VALUES (?, ?);", userUUID, neighborhoodid)
            session["neighborhood_check"] = "1"
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            nbhAdmin_db = db.execute("SELECT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid AND admin = 1;", neighborhoodid=neighborhoodid)
            if len(nbhAdmin_db) == 0:
                nbhAdmin = ""
            else:
                # log it to the first admin if there are multiple
                nbhAdmin = nbhAdmin_db[0]["useruuid"]
                if nbhAdmin == userUUID:
                    nbhAdmin = ""
            logHistory("neighborhood", "join", nbhAdmin, "", neighborhoodid, "")
            flash('Joined the neighborhood!')
            return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
        elif formAction == "edit":
            # ensure that the current user is an admin
            if admin_check(userUUID, neighborhoodid):
                return redirect("/editneighborhood?neighborhoodid=" + neighborhoodid)
            else:
                return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
        elif formAction == "managemembers":
            # ensure that the current user is an admin
            if admin_check(userUUID, neighborhoodid):
                return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
            else:
                return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
        elif formAction == "delete":
            # ensure that the current user is an admin
            if admin_check(userUUID, neighborhoodid):
                return redirect("/deleteneighborhood?neighborhoodid=" + neighborhoodid)
            else:
                return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
        elif formAction == "leave":
            # Refuse to let the only admin leave.
            admin_count = db.execute("SELECT * FROM memberships WHERE neighborhoodid = :neighborhoodid AND admin = 1;", neighborhoodid=neighborhoodid)
            if len(admin_count) == 1:
                flash("You are the only admin. There must be at least one admin to keep the nbh.")
                return redirect("/neighborhood_details?neighborhoodid=" + neighborhoodid)
            db.execute("DELETE FROM memberships WHERE useruuid = :userUUID AND neighborhoodid = :neighborhoodid;", userUUID=userUUID, neighborhoodid=neighborhoodid)
            # See if the user is a member of any neighborhoods anymore - if not, set to 0
            myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
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
            removeAllUserToolsFromNBH(userUUID, neighborhoodid)
            logHistory("neighborhood", "left", nbhAdmin, "", neighborhoodid, comment)
            flash('Left the neighborhood.')
            return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
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
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("neighborhood", "edittool", "", "", neighborhoodid, "updated tool visibilities")
            flash('Updated tool visibilities.')
            return redirect("/neighborhood_details?neighborhoodid=" + neighborhoodid)

        elif formAction == "cancel":
            return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
        else:
            return apology("Misc Error")


@neighborhoods_bp.route("/managemembers", methods=["GET", "POST"])
@login_required
@neighborhood_required
def managemembers():
    db = app.config["database_object"]
    '''Show user neighborhood details page'''
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

            # ensure that the current user is an admin
            if not admin_check(userUUID, neighborhoodid):
                return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')

            memberlist_db = db.execute("SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid AND banned = 0;", neighborhoodid=neighborhoodid)
            membercount = len(memberlist_db)
            allMembers = {}
            for i in range(len(memberlist_db)):
                memberinfo = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=memberlist_db[i]['useruuid'])[0]
                # skip the active user in the list
                if userUUID == memberlist_db[i]['useruuid']:
                    continue
                else:
                    isAdmin = admin_check(memberlist_db[i]['useruuid'], neighborhoodid)
                    info = {"uuid": memberlist_db[i]['useruuid'],
                            "username": memberinfo['username'],
                            "firstname": memberinfo['firstname'],
                            "isAdmin": isAdmin}
                    allMembers[memberlist_db[i]['useruuid']] = info

            bannedlist_db = db.execute("SELECT DISTINCT useruuid FROM memberships WHERE neighborhoodid = :neighborhoodid AND banned = 1;", neighborhoodid=neighborhoodid)
            bannedUsers = {}
            for i in range(len(bannedlist_db)):
                banneduserinfo = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=bannedlist_db[i]['useruuid'])[0]
                info = {"uuid": bannedlist_db[i]['useruuid'],
                        "username": banneduserinfo['username'],
                        "firstname": banneduserinfo['firstname']}
                bannedUsers[bannedlist_db[i]['useruuid']] = info

            return render_template("neighborhood/managemembers.html",
                                    openActions=countActions(),
                                    firstname=firstname,
                                    neighborhoodname=neighborhoodname,
                                    membercount=membercount,
                                    neighborhoodid=neighborhoodid,
                                    allMembers=allMembers,
                                    bannedUsers=bannedUsers)
    else:#POST
        formAction = request.form.get("returnedAction")
        print(formAction)
        if formAction == "sendMail":
            neighborhoodid = request.form.get("nbhid")
            # ensure that the current user is an admin
            if not admin_check(userUUID, neighborhoodid):
                return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
            return redirect(f"/sendmail?neighborhoodid={neighborhoodid}")
        elif formAction == "cancel":
            return redirect("/findtool")
        elif formAction == "addUser":
            actionDetails = request.form.get("actionDetails")
            neighborhoodid = request.form.get("nbhid")
            new_member = request.form.get("new_member")

            if new_member == "":
                flash("ERROR! Must provide a username or email")
                return redirect("/managemembers?neighborhoodid=" + neighborhoodid)

            #TODO TODO TODO!!!
            # look to see if a user exists with that username or email
            # if not, send an apology email or flash
            # if so, generate a joinNBH token,
            #   store that token in the database SOMEWHERE???
            #   send an email with a direct link with that token
            #   create an alert for the targetuuid
            return apology("TODO")
        elif formAction == "actionConfirmed":
            actionDetails = request.form.get("actionDetails")
            neighborhoodid = request.form.get("nbhid")

            if not admin_check(userUUID, neighborhoodid):
                # The active user is not the neighborhood admin
                flash("UNAUTHORIZED - must be an admin.")
                return redirect(url_for('neighborhoods_bp.neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

            [action, affectedusername] = actionDetails.split(";")
            affecteduserdeetz = db.execute("SELECT * FROM users WHERE username = :username;", username=affectedusername)[0]
            affectedUUID = affecteduserdeetz['uuid']
            #TODO Log all history events for these activities TODOTODOTODO
            #TODO flash events for all of these too.
            if action == "remove":
                # remove the user from the neighborhood
                db.execute("DELETE FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=affectedUUID, nbh=neighborhoodid)
                # delete all of their tool associations
                removeAllUserToolsFromNBH(affectedUUID, neighborhoodid)
                return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
            elif action == "banned":
                # ban the user from the NBH (delete any past associations with the NBH)
                db.execute("DELETE FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=affectedUUID, nbh=neighborhoodid)
                db.execute("INSERT INTO memberships (useruuid, neighborhoodid, banned) VALUES (?, ?, 1);", affectedUUID, neighborhoodid)
                # delete all of their tool associations
                removeAllUserToolsFromNBH(affectedUUID, neighborhoodid)
                # log the event in history
                return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
            elif action == "noAdmin":
                # revoke admin access to the NBH
                db.execute("UPDATE memberships SET admin = 0 WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=affectedUUID, nbh=neighborhoodid)
                return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
            elif action == "yesAdmin":
                # appoint admin access to the NBH
                db.execute("UPDATE memberships SET admin = 1 WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=affectedUUID, nbh=neighborhoodid)
                return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
            else:
                return apology("34994823", "Misc Error")
        elif formAction == "unban":
            actionDetails = request.form.get("actionDetails")
            neighborhoodid = request.form.get("nbhid")
            affectedusers = actionDetails.split(";")
            if len(affectedusers) == 0:
                return ('', 204)

            if not admin_check(userUUID, neighborhoodid):
                # The active user is not the neighborhood admin
                flash("UNAUTHORIZED - must be an admin.")
                return redirect(url_for('neighborhoods_bp.neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

            for affectedUUID in affectedusers:
                db.execute("DELETE FROM memberships WHERE useruuid = :uuid AND neighborhoodid = :nbh;", uuid=affectedUUID, nbh=neighborhoodid)
            return redirect("/managemembers?neighborhoodid=" + neighborhoodid)
        else:
            return apology("Misc Error")


@neighborhoods_bp.route("/editneighborhood", methods=["GET", "POST"])
@login_required
#@neighborhood_required
def editneighborhood():
    db = app.config["database_object"]
    '''Show user edit neighborhood page'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        neighborhoodid = request.args.get("neighborhoodid")
        if not neighborhoodid:
            return apology("Need to provide a neighborhood id")

        neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]

        if not admin_check(userUUID, neighborhoodid):
            # The active user is not the neighborhood admin
            flash("UNAUTHORIZED - cannot edit the neighborhood if not the admin.")
            return redirect(url_for('neighborhoods_bp.neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

        neighborhood = neighborhooddeetz["neighborhood"]
        zipcode = neighborhooddeetz["zip"]
        description = neighborhooddeetz["description"]
        privateCheck = neighborhooddeetz["private"]
        if check_password_hash(neighborhooddeetz["pwd"], ""):
            passwordYN = "No"
        else:
            passwordYN = "Yes"

        return render_template("neighborhood/editneighborhood.html", openActions=countActions(), firstname=firstname, neighborhood=neighborhood, zipcode=zipcode, description=description, privateCheck=privateCheck, passwordYN=passwordYN, neighborhoodid=neighborhoodid)
    else:
        neighborhoodid = request.form.get("neighborhoodid")
        neighborhood = request.form.get("neighborhood")
        private = request.form.get("private")
        zipcode = request.form.get("zipcode")
        description = request.form.get("description")
        password = generate_password_hash(request.form.get("password"))

        # update the database details for the given neighborhoodid
        db.execute("UPDATE neighborhoods SET neighborhood = ?, private = ?, zip = ?, description = ?, pwd = ? WHERE neighborhoodid = ?;", neighborhood, private, zipcode, description, password, neighborhoodid)
        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("neighborhood", "editneighborhood", "", "", neighborhoodid, "Neighborhood edited")
        flash("Successfully updated the neighborhood")
        return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')


@neighborhoods_bp.route("/deleteneighborhood", methods=["GET", "POST"])
@login_required
#@neighborhood_required
def deleteneighborhood():
    db = app.config["database_object"]
    '''confirm account deletion'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        neighborhoodid = request.args.get("neighborhoodid")
        neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]
        neighborhoodname = neighborhooddeetz['neighborhood']
        #confirm that the active user is an admin for the neighborhood, otherwise return unauthorized
        if not admin_check(userUUID, neighborhoodid):
            # The active user is not the neighborhood admin
            flash("UNAUTHORIZED - cannot delete the neighborhood if not the admin.")
            return redirect(url_for('neighborhoods_bp.neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

        return render_template("neighborhood/confirmdelete_nbh.html", openActions=countActions(), firstname=firstname, neighborhoodname=neighborhoodname, neighborhoodid=neighborhoodid)
    else:
        formAction = request.form.get("returnedAction")
        neighborhoodid = request.form.get("neighborhoodid")
        if formAction == "deleteNeighborhood":
            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid AND deleted = 0;", neighborhoodid=neighborhoodid)[0]
            if not admin_check(userUUID, neighborhoodid):
                # The active user is not the neighborhood admin
                flash("UNAUTHORIZED - cannot delete the neighborhood if not the admin.")
                return redirect(url_for('neighborhoods_bp.neighborhood_details') + '?neighborhoodid=' + neighborhoodid)

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
            # remove all tool visibility relationships to the deleted neighborhood
            #  actiually commented out so that if the "deleted" neighborhood is ever restored, the tool relationship will still be there
            #db.execute("DELETE FROM toolvisibility WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("neighborhood", "deleteneighborhood", "", "", neighborhoodid, "")
            flash('Neighborhood deleted.')
            return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')
        elif formAction == "cancel":
            return redirect("/neighborhood_details?neighborhoodid=" + neighborhoodid)
        else:
            return apology("Misc Error")


@neighborhoods_bp.route("/sendmail", methods=["GET", "POST"])
@login_required
@neighborhood_required
def sendmail():
    db = app.config["database_object"]
    '''confirm account deletion'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        neighborhoodid = request.args.get("neighborhoodid")
        if neighborhoodid:
            neighborhooddeetz = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)[0]
            neighborhoodName = neighborhooddeetz['neighborhood']
            userdeetz = db.execute("SELECT * FROM users WHERE uuid = :userUUID", userUUID=userUUID)[0]
            username = userdeetz['username']
            email = userdeetz['email']
            # ensure that the current user is an admin
            if not admin_check(userUUID, neighborhoodid):
                flash("UNAUTHORIZED - cannot message the neighborhood if not the admin.")
                return redirect(url_for('neighborhoods_bp.neighborhoods') + '#mine')

            return render_template("neighborhood/sendmail.html", openActions=countActions(), firstname=firstname, username=username, email=email, neighborhoodName=neighborhoodName, askall=False, neighborhood_send_list=neighborhoodid)

        mynbhlist = db.execute("SELECT * FROM neighborhoods WHERE neighborhoodid IN (SELECT neighborhoodid FROM memberships WHERE useruuid = :userUUID AND banned = 0) AND deleted = 0;", userUUID=userUUID)
        myneighborhoods = {}
        for row in mynbhlist:
            info = {'neighborhood': row["neighborhood"], 'neighborhoodid': row["neighborhoodid"]}
            myneighborhoods[row["neighborhoodid"]] = info
        userdeetz = db.execute("SELECT * FROM users WHERE uuid = :userUUID", userUUID=userUUID)[0]
        username = userdeetz['username']
        email = userdeetz['email']
        return render_template("neighborhood/sendmail.html", openActions=countActions(), firstname=firstname, myneighborhoods=myneighborhoods, username=username, email=email, askall=True)
    else:#POST
        formAction = request.form.get("returnedAction")
        if formAction == "sendMail":
            nbhChecks = request.form.getlist("nbhChecks")
            shareChecks = request.form.getlist("shareChecks")
            if len(nbhChecks) == 0:
                neighborhood_send_list = request.form.get("neighborhood_send_list")
                if neighborhood_send_list == "":
                    flash("You must pick at least one neighborhood.")
                    return apology("one neighborhood", "you must pick at least one")
                # send the email to the one preloaded into the form (admin mail)
                # ensure user is an admin
                if not admin_check(userUUID, neighborhood_send_list):
                    flash("UNAUTHORIZED - cannot message the neighborhood if not the admin.")
                    return redirect(url_for('neighborhoods_bp.neighborhods') + '#mine')
                #TODO send mail to nbh as admin
                print("Admin email to: " + neighborhood_send_list)
            else:
                ## TODO: for each NBH, ensure the user is a member
                ## TODO: send mail to many people
                print("Asking these neighborhoods: " + str(nbhChecks))
            if "email" in shareChecks:
                print("YES: share the email address")
            else:
                print("NO: don't share the email address")
            return apology("todo")
        elif formAction == "cancel":
            # return to the right place if coming from an admin message
            nbhChecks = request.form.getlist("nbhChecks")
            if len(nbhChecks) == 0:
                neighborhood_send_list = request.form.get("neighborhood_send_list")
                if neighborhood_send_list == "":
                    return redirect("/findtool")
                else:
                    if admin_check(userUUID, neighborhood_send_list):
                        return redirect("/managemembers?neighborhoodid=" + neighborhood_send_list)
                    else:
                        return redirect("/neighborhood_details?neighborhoodid=" + neighborhood_send_list)
            return redirect("/findtool")
        else:
            return apology("Misc Error")

