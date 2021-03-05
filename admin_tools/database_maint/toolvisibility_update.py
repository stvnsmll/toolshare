        # Administrative database manipulation:
        #  paste this into the main code somewhere to run
        '''   '''

        # get list of all users that are not deleted (allusers) - their uuids
        allusers = db.execute("SELECT uuid FROM users WHERE deleted IS 0;")

        print("\n\nSTARTING THE DB MAINTENENCE HERE!\n\n")

        for userUUID2 in allusers:
            #get their neighborhood list (NL)
            print(userUUID2['uuid'])
            NL = db.execute("SELECT neighborhoodid FROM memberships WHERE useruuid IS :userUUID2;", userUUID2=userUUID2['uuid'])
            print(NL)
            #get all of the user's tools (TL)
            TL = db.execute("SELECT toolid FROM tools WHERE owneruuid IS :userUUID AND deleted IS 0;", userUUID=userUUID2['uuid'])
            print(TL)

            for tool in TL:
                privateCheck = db.execute("SELECT private FROM tools WHERE toolid IS :tool AND deleted IS 0;", tool=tool['toolid'])[0]['private']
                print(privateCheck)
                # if tool is not marked as private (privateCheck = 0) then add a relationship for this tool to each neighborhood.
                if privateCheck == 0:
                    for nbh in NL:
                        print(nbh['neighborhoodid'])
                        print(tool['toolid'])
                        db.execute("INSERT OR IGNORE INTO toolvisibility (neighborhoodid, toolid) VALUES (?, ?);", nbh['neighborhoodid'], tool['toolid'])

        flash("database updated!")
        return redirect(url_for('index') + '#myTools')