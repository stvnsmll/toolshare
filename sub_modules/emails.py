#module for emails

#imports
import datetime
import uuid
from flask import current_app as app
from flask_mail import Message

from .helpers import logHistory
from .image_mgmt import get_image_s3



# generic send_mail([recipients], subject, message):
def send_mail(recipients, subject, message):
    mail = app.config["mail_object"]
    msg = Message(subject, sender = "sharetools.tk@gmail.com", recipients = recipients)
    msg.body = message
    msg.html = message.replace("\n","<br />\n")
    mail.send(msg)
    print("Mail Sent")


def requestApproved(actionid, comments):
    db = app.config["database_object"]
    SEND_EMAIL_ACTIONS = app.config["SEND_EMAIL_ACTIONS"]

    actiondetails = db.execute("SELECT * FROM actions WHERE actionid = :actionid;", actionid=actionid)[0]
    requestor = actiondetails['originuuid']
    targetuuid = actiondetails['targetuuid']
    toolid = actiondetails['toolid']
    # change the state of the actionid to show it is closed with closed date - add any comments
    db.execute("UPDATE actions SET state = 'closed', timestamp_close = :timeclose, messages = :comments WHERE actionid = :actionid;", timeclose=datetime.datetime.now(), comments=comments, actionid=actionid)
    # change the state of the tool to borrowed
    db.execute("UPDATE tools SET state = 'borrowed', activeuseruuid = :requestor WHERE toolid = :toolid;", requestor=requestor, toolid=toolid)
    # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
    logHistory("tool", "approve", "", toolid, "", comments)
    logHistory("tool", "borrow", requestor, toolid, "", comments)
    if SEND_EMAIL_ACTIONS == 1:
        # get more info for the email content
        tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]
        toolname = tooldetails["toolname"]
        ownerdetails = db.execute("SELECT * FROM users WHERE uuid = :toolowner;", toolowner=tooldetails["owneruuid"])[0]
        ownerfirstname = ownerdetails['firstname']
        ownerUUID = ownerdetails['uuid']

        recipientuuid = requestor
        subject = "Tool Share - Tool request approved"
        actionmsg = f"{ownerfirstname} has approved your request for the tool: {toolname}. It is now marked as borrowed by you."
        secondline = f"<p>You can now see their email address and possible other communication methods to setup and coordinate sharing the <a href='https://sharetools.tk/tool_details?toolid={toolid}'>tool</a>.</p>"
        send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline)

        recipientuuid = ownerUUID
        subject = "Tool Share - Tool marked borrowed"
        requesterdetails = db.execute("SELECT * FROM users WHERE uuid = :requestor;", requestor=requestor)[0]
        recipientfirstname = requesterdetails['firstname']
        actionmsg = f"{recipientfirstname} has borrowed your tool: {toolname}."
        secondline = f"<p>You can go in and require them to return it at anytime <a href='https://sharetools.tk/tool_details?toolid={toolid}'>here</a>.</p>"
        send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline)


def requestDenied(actionid, comments):
    db = app.config["database_object"]
    SEND_EMAIL_ACTIONS = app.config["SEND_EMAIL_ACTIONS"]

    actiondetails = db.execute("SELECT * FROM actions WHERE actionid = :actionid;", actionid=actionid)[0]
    requestor = actiondetails['originuuid']
    targetuuid = actiondetails['targetuuid']
    toolid = actiondetails['toolid']
    # change the state of the actionid to show it is closed with closed date - add any comments
    db.execute("UPDATE actions SET state = 'closed', timestamp_close = :timeclose, messages = :comments WHERE actionid = :actionid;", timeclose=datetime.datetime.now(), comments=comments, actionid=actionid)
    # change the state of the tool to borrowed
    db.execute("UPDATE tools SET state = 'available', activeuseruuid = NULL WHERE toolid = :toolid;", toolid=toolid)
    # log an event in the history DB table: >>logHistory(historyType, action, seconduuid, toolid, neighborhoodid, comment)<<
    logHistory("tool", "reject", "", toolid, "", comments)

    if SEND_EMAIL_ACTIONS == 1:
        # get more info for the email content
        tooldetails = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]
        toolname = tooldetails["toolname"]
        ownerdetails = db.execute("SELECT * FROM users WHERE uuid = :toolowner;", toolowner=tooldetails["owneruuid"])[0]
        ownerfirstname = ownerdetails['firstname']
        ownerUUID = ownerdetails['uuid']

        recipientuuid = requestor
        subject = "Tool Share - Tool request denied"
        actionmsg = f"{ownerfirstname} has rejected your request for the tool: {toolname}."
        secondline = "<p><a href='https://sharetools.tk/actions#requests'>Login</a> to see more about this action.</p>"
        send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline)


def generate_new_authcode(email):
    db = app.config["database_object"]
    authcode = str(uuid.uuid4().hex)[:6].upper()
    time_now = str(datetime.datetime.now())
    authcode_withtime = "Unregistered_Email" + ";" + authcode + ";" + time_now
    db.execute("UPDATE users SET validateemail = :authcode WHERE email = :email", authcode=authcode_withtime, email=email)
    send_email_auth(email, authcode)
    return authcode


def send_email_toolaction(toolid, recipientuuid, subject, actionmsg, secondline):
    db = app.config["database_object"]

    #actionmsg ideas:
    #   {othername} has requested to borrow your tool: <strong>{toolname}</strong>.
    #   You have requested to borrow {toolname}.
    #   {toolowner} has approved/rejected your request for the tool: {toolname}.
    #   {toolowner} requires that you return the tool: {toolname}.
    #secondline examples:
    #   <p>Have a look at the details or approve/reject <a href="https://sharetools.tk/actions">here</a>!</p>
    #   <p>You can go in and cancel the request at anytime <a href="https://sharetools.tk/tool_details?toolid={toolid}">here</a>.</p>
    #   "" <-leave it blank
    #   <p>You can now see their email address and possible other communication methods to setup and coordinate sharing the <a href="https://sharetools.tk/tool_details?toolid={toolid}">tool</a>.</p>
    #   <p>Please login and make sure you mark the tool as <a href="https://sharetools.tk/tool_details?toolid={toolid}">returned</a>.</p>

    #get the Info
    tooldeetz = db.execute("SELECT * FROM tools WHERE toolid = :toolid AND deleted = 0;", toolid=toolid)[0]
    toolowner = db.execute("SELECT * FROM users WHERE uuid = :uuid", uuid=tooldeetz['owneruuid'])[0]
    if tooldeetz['photo'] == "none":
        photo = "https://i.imgur.com/oXNuzWq.png"
    else:
        photo = get_image_s3(str(tooldeetz['toolid']) + ".jpeg", 604799)
    toolname = tooldeetz['toolname'].lower()
    toolownername = toolowner['firstname']
    #send the email
    recipients = [db.execute("SELECT * FROM users WHERE uuid = :uuid", uuid=recipientuuid)[0]['email']]
    subject = subject
    message = f"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN" "http://www.w3.org/TR/REC-html40/loose.dtd">
<html>
<head>
<title style="font-family: arial;">Tool Share - New Action</title>
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
<div style="font-weight: bold;font-size: 1.15em;margin-top: 5px;margin-bottom: 20px;">{toolownername}, you have a new action on Tool Share!</div>
<div>
<img style="width: 180px; height: 180px; border-radius: 15px;" src='{photo}' alt="no photo"><br>
</div>
<p>{actionmsg}</p>
{secondline}
<br>
<span style="font-size: small;">You can also check out your <a href="https://sharetools.tk/history">history</a> too.</span>
<br>
</div>
<div style="padding: 8px; width: 100%;">
<div style="font-size: 10px; color: #808080; text-align: center; width: 100%;">
You can manage your communication preferences under your <a href="https://sharetools.tk/communication">account settings</a>.<br>
#dontbeafoolborrowatool<br>
Copyright 2021 / ToolShare / All Rights Reserved
</div>
</div>
</div>
</body>
</html>
"""
    message = message.replace('\n', ' ').replace('\r', ' ')
    # Send welcome email with the proper authorization code
    send_mail(recipients, subject, message)



def send_email_auth(email, authcode):
    # Send welcome email
    # generic send_mail([recipients], subject, message)
    recipients = [email]
    subject = "ToolShare: authenticate your email address"
    print(authcode)
    message = f"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN" "http://www.w3.org/TR/REC-html40/loose.dtd">
<html>
<head>
<title style="font-family: arial;">Tool Share - Validate Email</title>
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
Please confirm this is a functional email by entering this one-time confirmation code back in the app or by simply clicking the link.
<br>
<span style="font-size: small;">
(the code and link are only valid for 2 minutes)
</span>
<div style="padding: 25px;">
<span style="border: 2px dashed #808080; border-radius: 8px; padding: 4px 3px 6px 7px; width: fit-content; color:#cc5500; font-size: 1.3em; font-weight: bold;"> {authcode}&nbsp;</span>
<br>
<br>
<span style="padding-left: 12px;">
or click this <a href="https://sharetools.tk/validateemail?email={email}&authcode={authcode}"> direct link</a>.
</span>
</div>
</div>
<div style="padding: 8px; width: 100%;">
<div style="font-size: 10px; color: #808080; text-align: center; width: 100%;">
You can manage your communication preferences under your <a href="https://sharetools.tk/communication">account settings</a>.<br>
#dontbeafoolborrowatool<br>
Copyright 2021 / ToolShare / All Rights Reserved
</div>
</div>
</div>
</body>
</html>
"""
    message = message.replace('\n', ' ').replace('\r', ' ')
    # Send welcome email with the proper authorization code
    send_mail(recipients, subject, message)



def send_email_welcome(email, firstname):
    # Send welcome email
    # generic send_mail([recipients], subject, message)
    recipients = [email]
    subject = "Welcome to ToolShare!"
    message = f"""\
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN" "http://www.w3.org/TR/REC-html40/loose.dtd">
<html>
<head>
<title style="font-family: arial;">Tool Share - Welcome</title>
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
<div style="font-weight: bold;font-size: 1.3em;margin-top: 5px;margin-bottom: 20px;">Welcome to Tool Share, {firstname}!</div>
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
<br>
Thanks, and welcome aboard!
</div>
<div style="padding: 8px; width: 100%;">
<div style="font-size: 10px; color: #808080; text-align: center; width: 100%;">
You can manage your communication preferences under your <a href="https://sharetools.tk/communication">account settings</a>.<br>
#dontbeafoolborrowatool<br>
Copyright 2021 / ToolShare / All Rights Reserved
</div>
</div>
</div>
</body>
</html>
"""
    message = message.replace('\n', ' ').replace('\r', ' ')
    # Send welcome email with the proper authorization code
    send_mail(recipients, subject, message)

