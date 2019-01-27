from .loop_report_parser import parse_loop_report, Sections
import os
import re
import json


class LoopReport:

    def parse_by_file(self, path: str, file_name: str) -> dict:
        try:
            return self.__parse(path, file_name)
        except IsADirectoryError:
            raise RuntimeError('The file path and name passed in is invalid.')
        except:
            raise

    def parse_by_directory(self, directory: dict) -> list:
        all_dict_list = []
        try:
            for file_name in os.listdir(directory):
                if file_name.endswith(".md"):
                    all_dict_list.append(self.__parse(directory, file_name))
            return all_dict_list
        except IsADirectoryError:
            raise RuntimeError('The file path and name passed in is invalid.')
        except:
            raise

    def __parse(self, path, file_name) -> dict:
        loop_report_dict= {}
        dict = parse_loop_report(f"{path}/{file_name}")
        loop_report_dict["file_name"] = file_name
        if Sections.LOOP_VERSION in dict:
            try:
                loop_report_dict["loop_version"] = dict[Sections.LOOP_VERSION][Sections.LOOP_VERSION]
            except:
                print("handled error loop_version")

        if Sections.DEVICE_DATA_MANAGER in dict:
            try:
                self.__device_data_manager = dict[Sections.DEVICE_DATA_MANAGER]
            except:
                print("handled error device data manager")

        if Sections.RILEY_LINK_DEVICE in dict:
            try:
                riley_link_device = dict[Sections.RILEY_LINK_DEVICE]
                loop_report_dict["radio_firmware"] = riley_link_device["radioFirmware"].strip()
                loop_report_dict["ble_firmware"] = riley_link_device["bleFirmware"].strip()
            except:
                print("handled error riley link device")

        if Sections.CARB_STORE in dict:
            try:
                carb_store = dict[Sections.CARB_STORE]
                loop_report_dict["carb_ratio_schedule"] = json.loads(carb_store["carbRatioSchedule"].replace("[", "{").
                                                         replace("]", "}").replace("{{", "{").replace("}}", "}"))

                default_absorption_times = json.loads(carb_store["defaultAbsorptionTimes"].replace("(", "{")
                                                      .replace(")", "}").replace("fast", '"fast"').
                                                      replace("medium", '"medium"').replace("slow", '"slow"'))
                loop_report_dict["default_absorption_times_fast"] = default_absorption_times["fast"]
                loop_report_dict["default_absorption_times_medium"] = default_absorption_times["medium"]
                loop_report_dict["default_absorption_times_slow"] = default_absorption_times["slow"]

                temp = carb_store["insulinSensitivitySchedule"].replace("[", "{").replace("]", "}").replace("{{", "{").\
                    replace("}}", "}").replace('"items": {{', '"items": [{').replace('"items": {', '"items": [{').\
                    replace("}}", "}]")\
                    .replace('}, "unit"', '}], "unit"').replace('}, "timeZone"', '}], "timeZone"')

                if temp[-1:] != '}':
                    temp = temp + '}'
                loop_report_dict["insuline_sensitivity_schedule"] = json.loads(temp)

            except:
                print("handled error carb store")

        if Sections.DOSE_STORE in dict:
            try:
                dose_store = dict[Sections.DOSE_STORE]
                basal_profile = json.loads(dose_store["basalProfile"].replace("[", "{").replace("]", "}").
                                                  replace("{{", "{").replace("}}", "}").replace(": {", ": [{").
                                                  replace("}}", "}]}").replace('}, "timeZone"', '}], "timeZone"'))
                loop_report_dict["basal_profile_time_zone"] = basal_profile['timeZone']
                loop_report_dict["basal_profile_time_items"] = basal_profile['items']

                loop_report_dict["insulin_model"] = re.search(r'Optional\((.+?)\(Exponential',
                                                                     dose_store["insulinModel"]).group(1)
                loop_report_dict["action_duration"] = re.search('actionDuration: (.+?), peakActivityTime',
                                                                       dose_store["insulinModel"]).group(1)

            except:
                print("handled error dose store")


        minimed_pump_manager = None
        omnipod_pump_manager = None
        if Sections.MINIMED_PUMP_MANAGER in dict or Sections.OMNIPOD_PUMP_MAANGER in dict:
            if Sections.MINIMED_PUMP_MANAGER in dict:
                try:
                    minimed_pump_manager = dict[Sections.MINIMED_PUMP_MANAGER]
                except:
                    print("handled error minimed pump manager")
            if Sections.OMNIPOD_PUMP_MAANGER in dict:
                try:
                    omnipod_pump_manager = dict[Sections.OMNIPOD_PUMP_MAANGER]
                except:
                    print("handled error omnipod pump manager")

            self.__set_pump_manager_type(loop_report_dict, minimed_pump_manager, omnipod_pump_manager)

        if Sections.WATCH_DATA_MANAGER in dict:
            try:
                watch_data_manager = dict[Sections.WATCH_DATA_MANAGER]
                loop_report_dict["is_watch_app_installed"] = watch_data_manager["isWatchAppInstalled"].strip()

            except:
                print("handled error watch data manager")

        if Sections.LOOP_DATA_MANAGER in dict:
            try:
                loop_data_manager = dict[Sections.LOOP_DATA_MANAGER]

                loop_report_dict["maximum_basal_rate_per_hour"] = \
                    re.search(r'maximumBasalRatePerHour: Optional\((.+?)\), maximumBolus',
                              loop_data_manager["settings"]).group(1)

                loop_report_dict["maxium_bolus"] = re.search(
                    r'maximumBolus: Optional\((.+?)\), suspendThreshold', loop_data_manager["settings"]).group(1)

                loop_report_dict["retrospective_correction_enabled"] = \
                    re.search('retrospectiveCorrectionEnabled: (.+?), retrospectiveCorrection',
                              loop_data_manager["settings"]).group(1)

                loop_report_dict["suspend_threshold"] = re.search(
                    r'Loop.GlucoseThreshold\(value: (.+?), unit', loop_data_manager["settings"]).group(1)

                start_index = loop_data_manager["settings"].index('suspendThreshold')
                end_index = loop_data_manager["settings"].index('retrospectiveCorrectionEnabled')
                substr = loop_data_manager["settings"][start_index:end_index]

                unit = substr.index('unit')
                start_index = unit + 6
                check = ""
                while check != ')':
                    unit += 1
                    check = substr[unit]
                loop_report_dict["suspend_threshold_unit"] = substr[start_index:unit]


                start_index = loop_data_manager["settings"].index('overrideRanges')
                end_index = loop_data_manager["settings"].index('maximumBasalRatePerHour')
                substr = loop_data_manager["settings"][start_index:end_index]

                workout = substr.index('workout')
                start_index = workout + 10
                check = ""
                while check != ']':
                    workout += 1
                    check = substr[workout]
                loop_report_dict["workout"] = eval(substr[start_index:workout + 1])

                premeal = substr.index('preMeal')
                start_index = premeal + 10
                check = ""

                while check != ']':
                    premeal += 1
                    check = substr[premeal]
                loop_report_dict["premeal"] = eval(substr[start_index:premeal + 1])

                return loop_report_dict

            except:
                print("handled error loop data manager")



    def __set_pump_manager_type(self, loop_report_dict, minimed_pump_manager, omnipod_pump_manager):
        if minimed_pump_manager:
            loop_report_dict["pump_manager_type"] = "minimed"
            loop_report_dict["pump_model"] = minimed_pump_manager["pumpModel"].strip()

        elif omnipod_pump_manager:
            loop_report_dict["pump_manager_type"] = "omnipod"
            loop_report_dict["pm_version"] = omnipod_pump_manager["pmVersion"].strip()
            loop_report_dict["pi_version"] = omnipod_pump_manager["piVersion"].strip()

        else:
            loop_report_dict["pump_manager_type"] = "unknown"



