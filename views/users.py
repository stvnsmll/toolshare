
#imports
import datetime
import uuid
import qrcode
import io
import base64
from flask import Blueprint, session, redirect, url_for, render_template, request, flash
from flask import current_app as app
from werkzeug.security import check_password_hash, generate_password_hash

from sub_modules.helpers import login_required, countActions, logHistory, apology, getDescriptionTool, getDescriptionNBH
from sub_modules.emails import generate_new_authcode, send_email_welcome, send_mail


#setup the blueprint for this section of the app
users_bp = Blueprint('users_bp', __name__)
#use as needed:   db = app.config["database_object"]




@users_bp.route("/login", methods=["GET", "POST"])
def login():
    db = app.config["database_object"]
    '''Log user in'''

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
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            # logHistory("other", "failedlogin1", "", "", "", "")
            #db.execute("INSERT INTO history (type, action, useruuid, timestamp) VALUES (?, ?, ?, ?);", "other", "failedlogin1", "unknown", datetime.datetime.now())
            return apology("invalid username and/or password.", 403)

        # This is being taken care of in the catch-all above
        if rows[0]["deleted"] == 1:
            # logHistory("other", "failedlogin2", "", "", "", "")
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
        myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
        if len(myneighborhoods) != 0:
            session["neighborhood_check"] = "1"
        else:
            session["neighborhood_check"] = "0"

        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        logHistory("other", "login", "", "", "", "")

        # Redirect user to home page
        flash('You were successfully logged in.')
        if next_url:
            return redirect(next_url)
        return redirect("/tools")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # logHistory("other", "pagevisit", "", "", "", "")
        #db.execute("INSERT INTO history (type, action, useruuid, timestamp) VALUES (?, ?, ?, ?);", "other", "pagevisit", "unknown", datetime.datetime.now())
        return render_template("general/login.html")


@users_bp.route("/logout", methods=["GET", "POST"])
def logout():
    '''Log user out'''
    if request.method == "POST":
        session.clear()
        return redirect("/")
    else:#GET
        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        if session.get("user_uuid") is not None:
            logHistory("other", "logout", "", "", "", "")
        # Forget any user_uuid
        session.clear()
        # Redirect user to login form
        flash('You were successfully logged out.')
        return redirect("/login")


@users_bp.route("/register", methods=["GET", "POST"])
def register():
    db = app.config["database_object"]
    '''Register user'''
    if request.method == "GET":
        return render_template("general/register.html")
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

        rows2 = db.execute("SELECT uuid FROM users WHERE email = ? AND deleted = 0;", email)
        if len(rows2) != 0:
            return apology("Try the forgot password option", "Email in use already")

        # generate a new UUID for the user
        new_uuid = uuid.uuid4().hex
        # generate uuid for email opt-out.
        optouttoken = uuid.uuid4().hex
        # Initiate the user with an unregistered_email:
        db.execute("INSERT INTO users (uuid, firstname, username, email, hash, validateemail, theme, email_optout) VALUES (?, ?, ?, ?, ?, ?, ?);", new_uuid, firstname, newUsername, email, generate_password_hash(password1), "unregistered_email", "newuser", optouttoken)
        # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
        db.execute("INSERT INTO history (type, action, useruuid, comment, timestamp) VALUES (?, ?, ?, ?, ?);", "other", "signup", new_uuid, "NEW USER!!", datetime.datetime.now())

        authcode = generate_new_authcode(email)

        session["firstname"] = firstname

        return redirect(f"/validateemail?email={email}")


@users_bp.route("/validateemail", methods=["GET", "POST"])
def validateemail():
    db = app.config["database_object"]
    code_timeout_limit = 2#minutes
    if session.get("user_uuid") is not None:
        flash("Already logged in...")
        return redirect("/tools")
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
            return redirect("/tools")
        # get the user's autorization code:
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
                # See if the user is a member of any neighborhoods
                myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
                if len(myneighborhoods) != 0:
                    session["neighborhood_check"] = "1"
                else:
                    session["neighborhood_check"] = "0"
                session["theme"] = new_user[0]["theme"]
                logHistory("other", "email_validated", "", "", "", "")

                if session["theme"] == "newuser":
                    # send the welcome email
                    session["theme"] = "light"
                    db.execute("UPDATE users SET theme = :newTheme WHERE uuid = :userUUID;", userUUID=session["user_uuid"], newTheme="light")
                    send_email_welcome(new_email, new_user[0]["firstname"])
                else:
                    flash(new_user[0]["firstname"] + ", your email has been validated.")

                # redirect back to the tools (root) page
                return redirect("/tools")

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
        return render_template("accountmgmt/validateemail.html", new_email=new_email, errormessage=errormessage)
    else:#POST
        formAction = request.form.get("returnedAction")
        new_email = request.form.get("useremail")
        if formAction == "resendCode":
            new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
            if len(new_user) != 1:
                return apology("Error: No user found")
            elif new_user[0]['validateemail'] == "":
                flash("Email already validated")
                return redirect("/tools")
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
                return redirect("/tools")
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
                return render_template("accountmgmt/validateemail.html", new_email=new_email, errormessage=errormessage)
            if input_authcode == valid_code:
                # accound validated
                db.execute("UPDATE users SET validateemail = '' WHERE uuid = :uuid", uuid=new_user[0]['uuid'])
                session["user_uuid"] = new_user[0]["uuid"]
                session["firstname"] = new_user[0]["firstname"]
                # See if the user is a member of any neighborhoods
                myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
                if len(myneighborhoods) != 0:
                    session["neighborhood_check"] = "1"
                else:
                    session["neighborhood_check"] = "0"
                session["theme"] = new_user[0]["theme"]
                logHistory("other", "email_validated", "", "", "", "")

                if session["theme"] == "newuser":
                    #send the welcome email
                    session["theme"] = "light"
                    db.execute("UPDATE users SET theme = :newTheme WHERE uuid = :userUUID;", userUUID=session["user_uuid"], newTheme="light")
                    send_email_welcome(new_email, new_user[0]["firstname"])
                else:
                    flash(new_user[0]["firstname"] + ", your email has been validated.")

                # redirect back to the tools (root) page
                flash(new_user[0]["firstname"] + ", your email has been validated.")
                return redirect("/tools")
            else:
                error = "incorrect"
                return redirect(f"/validateemail?email={new_email}&error={error}")

        else:
            return apology("Misc Error")


@users_bp.route("/manageaccount", methods=["GET", "POST"])
@login_required
def manageaccount():
    db = app.config["database_object"]
    '''Delete account, change password, etc'''
    userUUID = session.get("user_uuid")
    miscInfo = db.execute("SELECT firstname, username, email FROM users WHERE uuid = :userUUID;", userUUID=userUUID)[0]
    firstname = miscInfo["firstname"]
    username = miscInfo["username"]
    email = miscInfo["email"]
    scrollPos = 0
    if request.method == "GET":
        return render_template("accountmgmt/manageaccount.html", openActions=countActions(), firstname=firstname, username=username, email=email, scrollPos=scrollPos)
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
            return redirect("/tools")
        elif formAction == "toggleTheme":
            if session["theme"] == "light":
                session["theme"] = "dark"
            else:
                session["theme"] = "light"
            #set the preference for the user
            db.execute("UPDATE users SET theme = :newTheme WHERE uuid = :userUUID;", userUUID=userUUID, newTheme=session["theme"])
            scrollPos = request.form.get("pageoffset")
            return render_template("accountmgmt/manageaccount.html", openActions=countActions(), firstname=firstname, username=username, email=email, scrollPos=scrollPos)
        else:
            return apology("Misc Error")


@users_bp.route("/communication", methods=["GET", "POST"])
#@login_required <--managed internally to be url unsubscribed
def communication():
    db = app.config["database_object"]
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
                                return render_template("accountmgmt/communicationpreferences.html", openActions=countActions(), firstname=firstname)
                            else:
                                return render_template("accountmgmt/unsubscribed.html")
                        else:
                            return apology("Invalid opt-out token", "contact admin")
                    else:
                        #user was already opted out
                        if session.get("user_uuid") is not None:
                            flash("You have already opted out.")
                            userUUID = session.get("user_uuid")
                            firstname = session.get("firstname")
                            return render_template("accountmgmt/communicationpreferences.html", openActions=countActions(), firstname=firstname)
                        else:
                            return redirect("/login")
                else:
                    #user does not exist...
                    return redirect("/tools")
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
            return render_template("accountmgmt/communicationpreferences.html", openActions=countActions(), firstname=firstname, optout=optout, phonenumber=phonenumber, phonepref=phonepref, nbhemails=nbhemails)
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
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editcommprefs", "", "", "", "")
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")

@users_bp.route("/changepassword", methods=["GET", "POST"])
#@login_required <--managed internally
def changepassword():
    db = app.config["database_object"]
    '''change your password'''
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
                            return render_template("accountmgmt/updatepwd.html", recoverytoken=recoverytoken, email=email, verb=verb)
                        else:
                            flash("Password reset link has expired.")
            return redirect(url_for("users_bp.login"))
        else:
            userUUID = session.get("user_uuid")
            firstname = session.get("firstname")
            email = request.args.get("email")
            recoverytoken = request.args.get("recoverytoken")
            if ((email != None) or (recoverytoken != None)):
                flash("Already logged in, no password reset needed.")
                db.execute("UPDATE users SET recoverykey = '' WHERE uuid = :userUUID;", userUUID=userUUID)
                return redirect("/tools")
            return render_template("accountmgmt/updatepwd.html", openActions=countActions(), verb=verb, firstname=firstname)
    else:
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
                session["theme"] = userdeetz[0]["theme"]
                # See if the user is a member of any neighborhoods
                myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
                if len(myneighborhoods) != 0:
                    session["neighborhood_check"] = "1"
                else:
                    session["neighborhood_check"] = "0"
                # Update the user's password
                db.execute("UPDATE users SET hash = :newPW WHERE uuid = :userUUID;",
                           newPW=generate_password_hash(newPassword1), userUUID=session["user_uuid"])
                # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
                logHistory("other", "recoveredpassword", "", "", "", "")
                flash('Your password was reset.')
                return redirect("/tools")

            #ELSE, the user was just changing their password
            if session.get("user_uuid") is None:
                return redirect(url_for("users_bp.login"))
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
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editpassword", "", "", "", "")
            # show confirmation to user
            flash('Password successfully updated.')
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@users_bp.route("/changename", methods=["GET", "POST"])
@login_required
def changename():
    db = app.config["database_object"]
    '''change your firstname'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        return render_template("accountmgmt/updatename.html", openActions=countActions(), firstname=firstname)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "returnHome":
            return redirect("/manageaccount")
        elif formAction == "changename":
            # get the form data
            newName = request.form.get("newName")
            if not newName:
                flash('Must enter a name.')
                return render_template("accountmgmt/updatename.html", openActions=countActions(), firstname=firstname)
            if newName == firstname:
                flash('that is not a new name...')
                return render_template("accountmgmt/updatename.html", openActions=countActions(), firstname=firstname)

            # Update the user's name
            db.execute("UPDATE users SET firstname = :newName WHERE uuid = :userUUID;", newName=newName, userUUID=userUUID)
            session["firstname"] = newName
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editusername", "", "", "", "")
            # show confirmation to user
            flash('Name changed successfully.')
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@users_bp.route("/updateemail", methods=["GET", "POST"])
@login_required
def updateemail():
    db = app.config["database_object"]
    '''change your email'''
    userUUID = session.get("user_uuid")
    miscInfo = db.execute("SELECT firstname, email FROM users WHERE uuid = :userUUID;", userUUID=userUUID)[0]
    firstname = miscInfo["firstname"]
    oldEmail = miscInfo["email"]
    if request.method == "GET":
        return render_template("accountmgmt/updateemail.html", openActions=countActions(), firstname=firstname, oldEmail=oldEmail)
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "returnHome":
            return redirect("/manageaccount")
        elif formAction == "changeEmail":
            # get the form data
            newEmail = request.form.get("newEmail")
            if newEmail == "":
                flash('Must enter an email address.')
                return render_template("accountmgmt/updateemail.html", openActions=countActions(), firstname=firstname, oldEmail=oldEmail)
            if newEmail == oldEmail:
                flash("that's the same email address...")
                return render_template("accountmgmt/updateemail.html", openActions=countActions(), firstname=firstname, oldEmail=oldEmail)

            # Update the user's email
            db.execute("UPDATE users SET email = :newEmail WHERE uuid = :userUUID;", newEmail=newEmail, userUUID=userUUID)

            #require the user validate the new email address:
            authcode = generate_new_authcode(newEmail)

            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "editemail", "", "", "", "")
            # show confirmation to user
            session.clear()
            session["firstname"] = firstname
            #flash('Email changed successfully.')
            return redirect(f"/validateemail?email={newEmail}")
        else:
            return apology("Misc Error")


@users_bp.route("/deleteaccount", methods=["GET", "POST"])
@login_required
def deleteaccount():
    db = app.config["database_object"]
    '''confirm account deletion'''
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    if request.method == "GET":
        return render_template("/accountmgmt/confirmdelete.html", openActions=countActions(), firstname=firstname)
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
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "deleteuser", "", "", "", "")
            session.clear()
            flash('Your account was deleted.')
            return apology("to see you go!", "sorry")
        elif formAction == "returnHome":
            return redirect("/manageaccount")
        else:
            return apology("Misc Error")


@users_bp.route("/history", methods=["GET", "POST"])
@login_required
def history():
    db = app.config["database_object"]
    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    '''Show history of all tool and neighborhood related actions of the user'''

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
            neighborhoodnameDB = db.execute("SELECT neighborhood FROM neighborhoods WHERE neighborhoodid = :neighborhoodid;", neighborhoodid=neighborhoodid)
            if len(neighborhoodnameDB) != 1:
                neighborhoodname = "[deleted]"
            else:
                neighborhoodname = neighborhoodnameDB[0]['neighborhood']
            
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

        return render_template("accountmgmt/history.html", openActions=countActions(), firstname=firstname, toolhistory=toolhistory, nbhhistory=nbhhistory)

    else:
        return redirect("/manageaccount")


@users_bp.route("/sharelink", methods=["GET", "POST"])
@login_required
def sharelink():
    db = app.config["database_object"]
    if session.get("user_uuid") is None:
        return redirect("/")

    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    user_details = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=userUUID)[0]

    if request.method == "GET":
        link = request.args.get("link")
        #requesttype can be "nbh" for neighborhood or "tool" for a tool link
        print(link)
        if link.find("neighborhood_details") != -1:
            requesttype = "nbh"
        elif link.find("tool_details") != -1:
            requesttype = "tool"
        else:
            return apology("Misc error")

        itemID = link[(link.find("id=") + 3):]
        #the ID is the UUID for each item.


        if requesttype == "nbh":
            #ensure the active user is a member of the neighborhood
            accesscheck = db.execute("SELECT * from MEMBERSHIPS where useruuid = :userUUID AND neighborhoodid = :itemID AND banned = 0;", userUUID=userUUID, itemID=itemID)
            nbh_exists = db.execute("SELECT * from NEIGHBORHOODS where neighborhoodid = :itemID AND deleted = 0", itemID=itemID)
            if len(nbh_exists) == 0:
                accesscheck = []#make it an empty list to cancel the action
            if len(accesscheck) != 0:
                name = nbh_exists[0]["neighborhood"]
        elif requesttype == "tool":
            #ensure the active user is the tool owner
            accesscheck = db.execute("SELECT * from TOOLS where owneruuid = :userUUID AND toolid = :itemID AND deleted = 0", userUUID=userUUID, itemID=itemID)
            if len(accesscheck) != 0:
                name = accesscheck[0]["toolname"]
        if len(accesscheck) == 0:
            # no access or doesn't exist
            return redirect("/")

        #generate the QR code based on the incomming link.
        img = qrcode.make(link)
        data = io.BytesIO()
        img.save(data, "PNG")
        encoded_qr_image = base64.b64encode(data.getvalue())

        return render_template("general/sharelink.html", openActions=countActions(), firstname=firstname, qrcode_data=encoded_qr_image.decode('utf-8'), type=requesttype, name=name)
    else: #post
        return redirect("/tools")



@users_bp.route("/passwordrecovery", methods=["GET", "POST"])
def passwordrecovery():
    db = app.config["database_object"]
    '''Password Recovery'''
    if session.get("user_uuid") is not None:
        flash("Already logged in...")
        return redirect("/manageaccount")
    if request.method == "GET":
        return render_template("accountmgmt/passwordrecovery.html")
    else:
        formAction = request.form.get("returnedAction")
        if formAction == "resetPW":
            # first confirm that the email address is linked to an active user
            email = request.form.get("email")
            userdeetz = db.execute("SELECT * FROM users WHERE email = :email", email=email)
            if len(userdeetz) != 1:
                # no email with this account... but don't release this information
                return render_template("accountmgmt/passwordrecoverysent.html")
                #return apology("email check fail")

            # generate new recovery key, and set it to the user
            recoverykey = uuid.uuid4().hex
            db.execute("UPDATE users SET recoverykey = :key WHERE uuid = :userUUID;", key=recoverykey, userUUID=userdeetz[0]["uuid"])

            # send email with authcode
            recipients = [userdeetz[0]["email"]]
            subject = "ToolShare Password Reset"
            message = f'''\
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN" "http://www.w3.org/TR/REC-html40/loose.dtd">
<html>
<head>
<title style="font-family: arial;">Tool Share - Password Recovery</title>
</head>
<body style="margin: 0; background-color: #d3d3d3; border: 7px solid #d3d3d3;color: #000000;font-family: arial;">
<div style="background-color:#d3d3d3; width: 100%; height:max-content;">
<div style="width: 100%; height: 78px; background-color: #f8f9fa;font-family: arial;">
<a href="https://sharetools.tk" target="_blank" style="text-decoration: none;line-height: 78px;">
<img src='https://i.imgur.com/J5Rhl45.png' alt="icon" style="height: 58px;margin:10px 10px 10px 15px">
<span style="font-size:2.2em;display: inline;color: #cc5500;vertical-align: text-bottom;">ToolShare</span>
</a>
</div>
<div style="padding: 20px 10px 30px 10px; background-color: #ffffff;">
In order to reset the password to your ToolShare account, please click the link below.<br>
<span style="font-size: 0.8em;">If you did not request this password change, please log back in to confirm your account.</span>
<div style="padding: 25px;">
<span style="padding-left: 12px;">
<a href="https://sharetools.tk/changepassword?email={email}&recoverytoken={recoverykey}">Reset my password</a>
</span>
</div>
</div>
<div style="padding: 8px; width: 100%;">
<div style="font-size: 10px; color: #808080; text-align: center; width: 100%;">
#dontbeafoolborrowatool<br>
Copyright 2021 / ToolShare / All Rights Reserved
</div>
</div>
</div>
</body>
</html>
'''
            message = message.replace('\n', ' ').replace('\r', ' ')
            send_mail(recipients, subject, message)

            # redirect back to confirmation
            return render_template("accountmgmt/passwordrecoverysent.html")
        elif formAction == "returnHome":
            return redirect("/login")
        else:
            return apology("Misc Error")


@users_bp.route("/validatepwchange", methods=["GET", "POST"])
def validatePWchange():
    db = app.config["database_object"]
    code_timeout_limit = 2#minutes
    if session.get("user_uuid") is not None:
        flash("Already logged in...")
        return redirect("/tools")
    if request.method == "GET":
        new_email = request.args.get("email")
        error = request.args.get("error")
        if new_email == "" or new_email == None:
            return apology("not found","404")
        new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
        if len(new_user) != 1:
            return apology("No user found")
        elif new_user[0]['validateemail'] == "":
            flash("Email already validated")
            return redirect("/tools")
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
                myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
                if len(myneighborhoods) != 0:
                    session["neighborhood_check"] = "1"
                else:
                    session["neighborhood_check"] = "0"
                session["theme"] = new_user[0]["theme"]
                logHistory("other", "email_validated", "", "", "", "")
                # redirect back to the tools (root) page
                flash(new_user[0]["firstname"] + ", your email has been validated.")
                return redirect("/tools")
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
        return render_template("accountmgmt/validateemail.html", new_email=new_email, errormessage=errormessage)
    else:#POST
        formAction = request.form.get("returnedAction")
        new_email = request.form.get("useremail")
        if formAction == "resendCode":
            new_user = db.execute("SELECT * FROM users WHERE email = :email", email=new_email)
            if len(new_user) != 1:
                return apology("Error: No user found")
            elif new_user[0]['validateemail'] == "":
                flash("Email already validated")
                return redirect("/tools")
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
                return redirect("/tools")
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
                return render_template("accountmgmt/validateemail.html", new_email=new_email, errormessage=errormessage)
            if input_authcode == valid_code:
                # accound validated
                db.execute("UPDATE users SET validateemail = '' WHERE uuid = :uuid", uuid=new_user[0]['uuid'])
                session["user_uuid"] = new_user[0]["uuid"]
                session["firstname"] = new_user[0]["firstname"]
                myneighborhoods = db.execute("SELECT * FROM memberships WHERE useruuid = :userUUID AND banned = 0;", userUUID = session.get("user_uuid"))
                if len(myneighborhoods) != 0:
                    session["neighborhood_check"] = "1"
                else:
                    session["neighborhood_check"] = "0"
                session["theme"] = new_user[0]["theme"]

                if session["theme"] == "newuser":
                    #send the welcome email
                    session["theme"] = "light"
                    db.execute("UPDATE users SET theme = :newTheme WHERE uuid = :userUUID;", userUUID=session["user_uuid"], newTheme="light")
                    send_email_welcome(new_email, new_user[0]["firstname"])
                else:
                    flash(new_user[0]["firstname"] + ", your account has been recovered.")

                logHistory("other", "email_validated", "", "", "", "")
                # redirect back to the tools (root) page
                flash(new_user[0]["firstname"] + ", your account has been recovered.")
                return redirect("/tools")
            else:
                error = "incorrect"
                return redirect(f"/validateemail?email={new_email}&error={error}")

        else:
            return apology("Misc Error")


@users_bp.route("/ContactUs", methods=["GET", "POST"])
@login_required
def contactus():
    db = app.config["database_object"]
    if session.get("user_uuid") is None:
        return redirect("/contact")

    userUUID = session.get("user_uuid")
    firstname = session.get("firstname")
    user_details = db.execute("SELECT * FROM users WHERE uuid = :uuid;", uuid=userUUID)[0]
    email = user_details['email']
    username = user_details['username']

    if request.method == "GET":
        return render_template("general/ContactUs.html", openActions=countActions(), firstname=firstname, email=email, username=username)
    else: #post
        formAction = request.form.get("returnedAction")
        if formAction == "cancel":
            return redirect("/manageaccount")
        elif formAction == "sendMe":
            message = request.form.get("messsage")
            shareList = request.form.get("shareList")
            if message == "":
                flash("You must include something in the message box.")
                return render_template("general/ContactUs.html", openActions=countActions(), firstname=firstname, email=email, username=username)
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
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "feedback_email", "", "", "", "")
            flash("Your message has been sent, thank you!")
            return redirect("/manageaccount")
        else:
            return apology("Misc error")


#General contact form
@users_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if session.get("user_uuid") is not None:
        return redirect("/ContactUs")

    if request.method == "GET":
        requesttype = request.args.get("type")
        demoRequested = False
        if requesttype == "requestdemo":
            demoRequested = True
        return render_template("general/contact.html", demoRequested=demoRequested)
    else: #POST
        #TODO - make the general contact form live
        return apology("not setup yet", "todo")
        formAction = request.form.get("returnedAction")
        if formAction == "cancel":
            return redirect("/manageaccount")
        elif formAction == "sendMe":
            message = request.form.get("messsage")
            shareList = request.form.get("shareList")
            if message == "":
                flash("You must include something in the message box.")
                return render_template("general/general/ContactUs.html", openActions=countActions(), firstname=firstname, email=email, username=username)
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
            # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
            logHistory("other", "feedback_email", "", "", "", "")
            flash("Your message has been sent, thank you!")
            return redirect("/manageaccount")
        else:
            return apology("Misc error")


@users_bp.route("/TermsAndConditions")
def termsandconditions():
    if session.get("user_uuid") is None:
        firstname = ""
        openActions = 0
    else:
        firstname = session.get("firstname")
        openActions = countActions()
    return render_template("general/TermsAndConditions.html", openActions=openActions, firstname=firstname)


@users_bp.route("/PrivacyPolicy")
def privacypolicy():
    if session.get("user_uuid") is None:
        firstname = ""
        openActions = 0
    else:
        firstname = session.get("firstname")
        openActions = countActions()
    return render_template("general/PrivacyPolicy.html", openActions=openActions, firstname=firstname)


@users_bp.route("/FAQ")
@users_bp.route("/FAQ/")
@users_bp.route("/FAQ/<subpage>")
def FAQ(subpage='none'):
    if session.get("user_uuid") is None:
        firstname = ""
        openActions = 0
    else:
        firstname = session.get("firstname")
        openActions = countActions()

    if subpage == 'none':
        return render_template("/FAQs/FAQ_home.html", openActions=openActions, firstname=firstname, subpage=subpage)
    elif subpage == 'no_page':
        return apology("is under construction", "sorry, this help page")
    else:
        FAQ_path = "/FAQs/pages/" + subpage + ".html"
        return render_template(FAQ_path, openActions=openActions, firstname=firstname, subpage=subpage)

