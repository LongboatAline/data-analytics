#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
description: provide daily feedback to clinicians
version: 0.0.1
created: 2018-08-01
author: Ed Nykaza
dependencies:
    * requires tidepool-analytics-env (see readme for instructions)
    * requires a clinician or study username (email) and password
    * requires tidals (tidepool data analytics tools)
license: BSD-2-Clause
"""


# %% REQUIRED LIBRARIES
import pandas as pd
import numpy as np
import os
import sys
import requests
import json
import argparse
from pytz import timezone
from datetime import timedelta
import datetime as dt
import subprocess as sub
sys.path.insert(0, os.path.abspath(os.path.join(__file__, "..", "..", "..")))
import tidals as td


# %% USER INPUTS
codeDescription = "Provide daily feedback to clinicians"

parser = argparse.ArgumentParser(description=codeDescription)

parser.add_argument("-d",
                    "--date-stamp",
                    dest="dateStamp",
                    default=dt.datetime.now().strftime("%Y-%m-%d"),
                    help="date of the daily report, defaults to current date")

parser.add_argument("-e",
                    "--email",
                    dest="email",
                    default=np.nan,
                    help="the email address of the master clinicain or study account")

parser.add_argument("-p",
                    "--password",
                    dest="password",
                    default=np.nan,
                    help="the passwordof the master clinicain or study account")

parser.add_argument("-o",
                    "--output-data-path",
                    dest="outputPath",
                    default=os.path.join(".", "data"),
                    help="the output path where the data is stored")

args = parser.parse_args()


# %% CHECK/DECLARE INPUTS AND OUTPUT VARIABLES

if pd.isnull(args.email):
    sys.exit("missing email address: this function requires an email as an input")

if pd.isnull(args.password):
    sys.exit("missing password: this function requires a password as an input")

# create output folder if it doesn't exist
if not os.path.isdir(args.outputPath):
    os.makedirs(args.outputPath)

# create a report output folder if it doesn't exist
reportDate = args.dateStamp
reportPath = os.path.join(args.outputPath, "reports")
reportOutputPath = os.path.join(reportPath, reportDate)
if not os.path.isdir(reportPath):
    os.makedirs(reportPath)
    os.makedirs(reportOutputPath)

indvidualDataFolder = os.path.join(reportOutputPath, "individual-data-files")
if not os.path.isdir(indvidualDataFolder):
    os.makedirs(indvidualDataFolder)

# create a metadata output folder if it doesn't exist
metadataPath = os.path.join(args.outputPath, "metadata", reportDate)
jsonDataPath = os.path.join(metadataPath, "jsonData")
if not os.path.isdir(metadataPath):
    os.makedirs(metadataPath)
    os.makedirs(jsonDataPath)

allStats = pd.DataFrame()
metaData = pd.DataFrame(columns=["userID",
                                 "studyID",
                                 "getData.response1",
                                 "getData.response2",
                                 "nDuplicatesRemoved"])


# %% FUNCTIONS
def get_stats(df):
    statDF = pd.DataFrame(index=[0])
    statDF["totalNumberCBGValues"] = df.mg_dL.count()

    statDF["mean_mgdL"] = df.mg_dL.mean()
    statDF["std_mgdL"] = df.mg_dL.std()
    statDF["cov_mgdL"] = statDF["std_mgdL"] / statDF["mean_mgdL"]

    statDF["totalBelow54"] = sum(df.mg_dL < 54)
    statDF["totalBelow70"] = sum(df.mg_dL < 70)
    statDF["total54to70"] = sum((df.mg_dL >= 54) & (df.mg_dL < 70))
    statDF["total70to140"] = sum((df.mg_dL >= 70) & (df.mg_dL <= 140))
    statDF["total70to180"] = sum((df.mg_dL >= 70) & (df.mg_dL <= 180))
    statDF["total180to250"] = sum((df.mg_dL > 180) & (df.mg_dL <= 250))
    statDF["totalAbove180"] = sum(df.mg_dL > 180)
    statDF["totalAbove250"] = sum(df.mg_dL > 250)

    statDF["percentBelow54"] = statDF["totalBelow54"] / statDF["totalNumberCBGValues"]
    statDF["percentBelow70"] = statDF["totalBelow70"] / statDF["totalNumberCBGValues"]
    statDF["percent70to140"] = statDF["total70to140"] / statDF["totalNumberCBGValues"]
    statDF["percent70to180"] = statDF["total70to180"] / statDF["totalNumberCBGValues"]
    statDF["percentAbove180"] = statDF["totalAbove180"] / statDF["totalNumberCBGValues"]
    statDF["percentAbove250"] = statDF["totalAbove250"]  / statDF["totalNumberCBGValues"]

    statDF["min_mgdL"] = df.mg_dL.min()
    statDF["median_mgdL"] = df.mg_dL.describe()["50%"]
    statDF["max_mgdL"] = df.mg_dL.max()

    # calculate the start and end time of the cbg data
    startTime = df["localTime"].min()
    statDF["startTime"] = startTime
    endTime = df["localTime"].max()
    statDF["endTime"] = endTime
    statDF["totalNumberPossibleCBGvalues"] = len(pd.date_range(startTime, endTime, freq="5min"))

    # feedback criteria
    # A.  incomplete dataset
    statDF["percentOfExpectedData"] = \
        (((endTime - startTime).days * 86400) +
         ((endTime - startTime).seconds)) / (86400 - (5*60))

    if statDF.loc[0, "percentOfExpectedData"] < 0.834:  # greater than 4 hours of expected data
        statDF["GTE4hoursNoCgmSignal"] = "NA"
        statDF["incompleteDataset"] = "FLAG (" + \
            str(round(statDF.loc[0, "percentOfExpectedData"] * 100, 1)) + "%)"
    else:
        statDF["incompleteDataset"] = np.nan

        # 1.  >=4 hours without CGM signal
        missingCgm = statDF["totalNumberPossibleCBGvalues"] - statDF["totalNumberCBGValues"]
        if missingCgm[0] > (4 * 60 / 5):
            statDF["GTE4hoursNoCgmSignal"] = "FLAG"
        else:
            statDF["GTE4hoursNoCgmSignal"] = np.nan

    # 2.  >= 2 hours 54 <= BG < 70 mg/dl
    if statDF.loc[0, "total54to70"] > (2 * 60 / 5):
        statDF["GTE2hoursBetween54to70"] = \
            "FLAG (" + str(round(statDF.loc[0, "GTE2hoursBetween54to70"] * 5)) + "min)"
    else:
        statDF["GTE2hoursBetween54to70"] = np.nan

    # 3.  >= 15 minutes < 54 mg/dl"
    if statDF.loc[0, "totalBelow54"] > (15 / 5):
        statDF["GTE15minBelow54"] = "FLAG (" + str(round(statDF.loc[0, "totalBelow54"] * 5)) + "min)"
    else:
        statDF["GTE15minBelow54"] = np.nan

    return statDF


def sort_and_pretty_stat_output(df):

    for col in list(df):
        if (("percent" in col) | ("cov" in col)):
            df[col] = round(df[col] * 100, 1)

    for col in ["mean_mgdL", "std_mgdL"]:
        df[col] = round(df[col], 1)

    df = df[["studyID",
             "incompleteDataset",
             "GTE4hoursNoCgmSignal",
             "GTE2hoursBetween54to70",
             "GTE15minBelow54",
             "totalNumberCBGValues",
             "totalNumberPossibleCBGvalues",
             "startTime",
             "endTime",
             "percentOfExpectedData",
             "mean_mgdL",
             "std_mgdL",
             "cov_mgdL",
             "min_mgdL",
             "median_mgdL",
             "max_mgdL",
             "percentBelow54",
             "percentBelow70",
             "percent70to140",
             "percent70to180",
             "percentAbove180",
             "percentAbove250",
             "totalBelow54",
             "totalBelow70",
             "total54to70",
             "total70to140",
             "total70to180",
             "total180to250",
             "totalAbove180",
             "totalAbove250"]]

    return df


def get_timeZoneOffset(currentDate, userTz):
    tz = timezone(userTz)
    tzoNum = int(tz.localize(pd.to_datetime(currentDate) + timedelta(days=1)).strftime("%z"))
    tzoHours = np.floor(tzoNum / 100)
    tzoMinutes = round((tzoNum / 100 - tzoHours) * 100, 0)
    tzoSign = np.sign(tzoHours)
    tzo = int((tzoHours * 60) + (tzoMinutes * tzoSign))
    return tzo


def get_donor_lists(email, password, outputDonorList):
    p = sub.Popen(["getusers", email,
                   "-p", password, "-o",
                   outputDonorList, "-v"], stdout=sub.PIPE, stderr=sub.PIPE)

    output, errors = p.communicate()
    output = output.decode("utf-8")
    errors = errors.decode("utf-8")

    if output.startswith("Successful login.\nSuccessful") is False:
        sys.exit("ERROR with" + email +
                 " ouput: " + output +
                 " errorMessage: " + errors)

    return


def load_donors(outputDonorList):
    donorList = []
    if os.stat(outputDonorList).st_size > 0:
        donorList = pd.read_csv(outputDonorList,
                                header=None,
                                usecols=[0, 1],
                                names=["userID", "name"],
                                low_memory=False)

    return donorList


def get_json_data(email, password, userid, outputFilePathName, startDate, endDate):
    url1 = "https://api.tidepool.org/auth/login"
    myResponse = requests.post(url1, auth=(email, password))

    if(myResponse.ok):
        xtoken = myResponse.headers["x-tidepool-session-token"]
        url2 = "https://api.tidepool.org/data/" + userid + \
            "?endDate=" + endDate.strftime("%Y-%m-%d") + \
            "T23:59:59.000Z&startDate=" + \
            startDate.strftime("%Y-%m-%d") + "T00:00:00.000Z"

        headers = {
            "x-tidepool-session-token": xtoken,
            "Content-Type": "application/json"
            }

        myResponse2 = requests.get(url2, headers=headers)
        if(myResponse2.ok):

            usersData = json.loads(myResponse2.content.decode())
            with open(outputFilePathName, "w") as outfile:
                json.dump(usersData, outfile)

            print("successfully downloaded to " + outputFilePathName)

        else:
            print("ERROR", myResponse2.status_code)
    else:
        print("ERROR", myResponse.status_code)

    return myResponse, myResponse2


# %% START OF CODE
# get the list of donors if it doesn't already exist
outputDonorList = os.path.join(args.outputPath, "PHI-study-participants.csv")
if not os.path.exists(outputDonorList):
    get_donor_lists(args.email, args.password, outputDonorList)

    # load in the donor list
    studyPartipants = load_donors(outputDonorList)
    studyPartipants = studyPartipants[studyPartipants["name"] !=
                          "James Jellyfish"].sort_values("name").reset_index(drop=True)
    studyPartipants.to_csv(outputDonorList, index_label="dIndex")
else:
    studyPartipants = pd.read_csv(outputDonorList, index_col="dIndex", low_memory=False)

for dIndex in studyPartipants.index:
    userID = studyPartipants.userID[dIndex]
    studyID = studyPartipants["name"][dIndex]
    metaData.loc[dIndex, ["userID", "studyID"]] = userID, studyID

    outputFileLocation = os.path.join(jsonDataPath, "PHI-" + userID + ".json")

    startDate = pd.to_datetime(reportDate) - pd.Timedelta(2, unit="D")
    endDate = pd.to_datetime(reportDate) + pd.Timedelta(1, unit="D")

    reponse1, reponse2 = \
        get_json_data(args.email, args.password, userID, outputFileLocation, startDate, endDate)

    metaData.loc[dIndex, ["getData.response1", "getData.response2"]] = \
        reponse1.status_code, reponse2.status_code

    # load json data
    data = pd.read_json(outputFileLocation)

    if "type" in list(data):
        if "cbg" in data.type.unique():

            # calculate stats
            cgmData = data[data.type == "cbg"].copy()
            cgmData["utcTime"] = pd.to_datetime(cgmData.time, utc=True)

            # get data from 6am to 6am
            if (("timezone" in list(data)) | ("timezoneOffset" in list(data))):
                if "timezone" in list(data):
                    userTz = data.timezone.describe()["top"]
                    tzo = get_timeZoneOffset(reportDate, userTz)
                    tz = timezone(userTz)

                    start6amDate = tz.localize(pd.to_datetime(reportDate)
                                               - pd.Timedelta(1, unit="D")
                                               + pd.Timedelta(5, unit="h")
                                               + pd.Timedelta(57, unit="m")
                                               + pd.Timedelta(30, unit="s"))

                    end6amDate = tz.localize(pd.to_datetime(reportDate)
                                             + pd.Timedelta(5, unit="h")
                                             + pd.Timedelta(57, unit="m")
                                             + pd.Timedelta(30, unit="s"))

                    cgm = cgmData.loc[((cgmData.utcTime > start6amDate) &
                                       (cgmData.utcTime < end6amDate)), ["time", "value"]]

                else:  # if there is no timezone given, then infer from timezone offset
                    tzo = data.timezoneOffset.median()
                    start6amDate = (pd.to_datetime(reportDate)
                                    - pd.Timedelta(1, unit="D")
                                    + pd.Timedelta(5, unit="h")
                                    + pd.Timedelta(57, unit="m")
                                    + pd.Timedelta(30, unit="s")
                                    - pd.Timedelta(tzo, unit="m"))

                    end6amDate = (pd.to_datetime(reportDate)
                                  + pd.Timedelta(5, unit="h")
                                  + pd.Timedelta(57, unit="m")
                                  + pd.Timedelta(30, unit="s")
                                  - pd.Timedelta(tzo, unit="m"))

                    cgm = cgmData.loc[((pd.to_datetime(cgmData.time) > start6amDate) &
                                       (pd.to_datetime(cgmData.time) < end6amDate)), ["time", "value"]]

                cgm = cgm.rename(columns={"value": "mmol_L"})
                cgm["mg_dL"] = (cgm["mmol_L"] * 18.01559).astype(int)

                # round time to the nearest 5 minutes
                cgm = td.round_time(cgm)

                # drop any duplicates
                cgm, nDuplicatesRemoved = td.remove_duplicates(cgm, cgm["roundedTime"])
                metaData.loc[dIndex, ["nDuplicatesRemoved"]] = nDuplicatesRemoved

                cgm["localTime"] = cgm["roundedTime"] + pd.to_timedelta(tzo, unit="m")

                if len(cgm) > 0:

                    stats = get_stats(cgm)

                    # save raw data
                    cgm = cgm.sort_values("localTime").reset_index(drop=True)
                    cgm = cgm.rename(columns={"localTime": "roundedLocalTime"})
                    cgm = cgm[["time", "roundedLocalTime", "mmol_L", "mg_dL"]]
                    cgm.to_csv(os.path.join(indvidualDataFolder,
                               reportDate + "-cgm-data-for-" + studyID + ".csv"))

                else:
                    stats = pd.DataFrame(index=[dIndex])
                    stats["incompleteDataset"] = "no cgm data"

            else:
                stats = pd.DataFrame(index=[dIndex])
                stats["incompleteDataset"] = "no timezone information"
        else:
            stats = pd.DataFrame(index=[dIndex])
            stats["incompleteDataset"] = "no data"
    else:
        stats = pd.DataFrame(index=[dIndex])
        stats["incompleteDataset"] = "no data"

    stats["studyID"] = studyID
    allStats = pd.concat([allStats, stats], ignore_index=True, sort=False)

# sort and save output
feedback = sort_and_pretty_stat_output(allStats)

feedback.to_csv(os.path.join(reportOutputPath, reportDate + "-cgm-report.csv"), index=False)
metaData.to_csv(os.path.join(metadataPath, "PHI-" + reportDate + "-metaData.csv"))
