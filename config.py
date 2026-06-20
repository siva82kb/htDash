import os
from datetime import timedelta
import pytz

class Config:
    # Path configurations
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    META_DATA_PATH = os.path.join(BASE_DIR, "META-DATA")
    LOG_DIR = "user_logs"
    DEVICE_CONFIG_PATH = "./static/data/device_config.json"

    # New data folder structure
    DATA_ROOT = os.environ.get('DATA_ROOT', './data')
    HOSPITALS = ['manipal', 'ranipet', 'ludhiana']
    PATIENT_META_FILE = '{patient_id}.json'  # filename matches the patient ID

    # Maps Flask session login_place → data folder name
    HOSPITAL_FOLDER_MAP = {
        'Manipal':  'manipal',
        'Ranipet':  'ranipet',
        'Ludhiana': 'ludhiana',
    }

    # Timezone configuration: India Standard Time (IST) for all three hospitals
    # All hospitals are in India, so they all use IST (UTC+5:30)
    TIMEZONE = pytz.timezone('Asia/Kolkata')  # IST - UTC+5:30
    # Override with environment variable if needed: TZ='Asia/Kolkata'
    # Or set via OS: export TZ='Asia/Kolkata'
    
    # Device labels
    PLUTO_LABEL = 'Pluto'
    MARS_LABEL = 'Mars'
    ACTILIFE_LABEL = 'actilife'
    ADMIN_LOGIN = 'admin'
    
    # File names
    HOMER_ID_DETAILS = "homerIdDetails.json"
    DATES_FOLDER = "Dates"
    CONFIG_DATA = "configdata.csv"
    CONTROL_USER_DETAILS = "controlUserDetails.csv"
    
    # CSV headers
    PLUTO_CONFIG_HEADER = ["HomerID", "StartDate", "EndDate", "TotalTime", "WFE", "WURD", "FPS", "HOC", "FME1", "FME2", "TrainingSide", "Location", "Group", "FME1K", "FME2K"]
    MARS_CONFIG_HEADER = ["HomerID", "StartDate", "EndDate", "TotalTime", "ML", "AP", "MLAP", "ForeArmLength", "UpperArmLength", "TrainingSide", "Location", "Group"]
    ACTILIFE_CONFIG_HEADER = ["HomerID", "StartDate", "EndDate", "Location", "Group"]
    
    # Mechanisms
    PLUTO_MECHANISMS = ["WFE", "WURD", "FPS", "HOC", "FME1", "FME2"]
    MARS_MECHANISMS = ["ML", "AP", "MLAP"]
    
    # AWS
    BUCKET_NAME = 'homerclouds'
    # Set USE_S3=true in production to store all data/ files in S3.
    # Set USE_S3=false (default) for local development — data/ folder is used instead.
    USE_S3 = os.environ.get('USE_S3', 'false').lower() == 'true'
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-in-production'
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    # Set True in development to cache session in browser localStorage (survives server restarts).
    # Set False in production — server session is the sole source of truth.
    USE_LOCAL_STORAGE = os.environ.get('USE_LOCAL_STORAGE', 'true').lower() == 'true'
    
    # Login credentials
    LOGIN_CREDENTIALS = {
        "MP-HS-1001": {"place": "Manipal", "privilege": "user", "password": "manipal@123"},
        "RP-HS-1002": {"place": "Ranipet", "privilege": "user", "password": "ranipet@123"},
        "LD-HS-1003": {"place": "Ludhiana", "privilege": "user", "password": "ludhiana@123"},
        "LAB-HS-DATA": {"place": "admin", "privilege": "admin", "password": "lab@123"},
        "MP-HS-ADMIN": {"place": "Manipal", "privilege": "admin", "password": "manipaladmin@123"},
        "RP-HS-ADMIN": {"place": "Ranipet", "privilege": "admin", "password": "ranipetadmin@123"},
        "LD-HS-ADMIN": {"place": "Ludhiana", "privilege": "admin", "password": "ludhianaadmin@123"},
    }
    
    # Exercise Library
        # Exercise Library (expanded version)
    EXERCISE_LIBRARY = {
        "VCG2": {
            "name": "VCG2 - Basic Exercises",
            "programs": {
                "shoulder_flexion": {
                    "name": "Shoulder Flexion Program",
                    "exercises": [
                        {
                            "id": "sf1",
                            "short_name": "Shoulder Flexion 1",
                            "full_name": "Shoulder Flexion Exercise 1",
                            "description": "Raise arm forward to shoulder level",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 10,
                            "default_sets": 3,
                            "default_duration": "30 seconds"
                        },
                        {
                            "id": "sf2",
                            "short_name": "Shoulder Flexion 2",
                            "full_name": "Shoulder Flexion Exercise 2",
                            "description": "Raise arm sideways to shoulder level",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 10,
                            "default_sets": 3,
                            "default_duration": "30 seconds"
                        }
                    ]
                },
                "elbow_flexion": {
                    "name": "Elbow Flexion Program",
                    "exercises": [
                        {
                            "id": "ef1",
                            "short_name": "Elbow Flexion 1",
                            "full_name": "Elbow Flexion Exercise 1",
                            "description": "Bend elbow to touch shoulder",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 15,
                            "default_sets": 3,
                            "default_duration": "20 seconds"
                        },
                        {
                            "id": "ef2",
                            "short_name": "Elbow Flexion 2",
                            "full_name": "Elbow Flexion Exercise 2",
                            "description": "Alternating elbow flexion",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 12,
                            "default_sets": 3,
                            "default_duration": "25 seconds"
                        }
                    ]
                },
                "wrist_movements": {
                    "name": "Wrist Movement Program",
                    "exercises": [
                        {
                            "id": "wm1",
                            "short_name": "Wrist Flexion",
                            "full_name": "Wrist Flexion Exercise",
                            "description": "Flex wrist up and down",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 15,
                            "default_sets": 3,
                            "default_duration": "20 seconds"
                        },
                        {
                            "id": "wm2",
                            "short_name": "Wrist Extension",
                            "full_name": "Wrist Extension Exercise",
                            "description": "Extend wrist with resistance",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 12,
                            "default_sets": 3,
                            "default_duration": "25 seconds"
                        }
                    ]
                }
            }
        },
        "VCG3": {
            "name": "VCG3 - Intermediate Exercises",
            "programs": {
                "shoulder_strength": {
                    "name": "Shoulder Strengthening Program",
                    "exercises": [
                        {
                            "id": "ss1",
                            "short_name": "Shoulder Press",
                            "full_name": "Shoulder Press with Resistance",
                            "description": "Press weight overhead",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 8,
                            "default_sets": 3,
                            "default_duration": "30 seconds"
                        },
                        {
                            "id": "ss2",
                            "short_name": "Lateral Raises",
                            "full_name": "Lateral Raise Exercise",
                            "description": "Raise arms sideways with resistance",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 10,
                            "default_sets": 3,
                            "default_duration": "25 seconds"
                        }
                    ]
                },
                "elbow_extension": {
                    "name": "Elbow Extension Program",
                    "exercises": [
                        {
                            "id": "ee1",
                            "short_name": "Tricep Extension",
                            "full_name": "Tricep Extension Exercise",
                            "description": "Extend elbow against resistance",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 10,
                            "default_sets": 3,
                            "default_duration": "20 seconds"
                        }
                    ]
                }
            }
        },
        "VCG4,5": {
            "name": "VCG4,5 - Advanced Exercises",
            "programs": {
                "functional_training": {
                    "name": "Functional Training Program",
                    "exercises": [
                        {
                            "id": "ft1",
                            "short_name": "Reaching Overhead",
                            "full_name": "Overhead Reaching Exercise",
                            "description": "Reach for objects overhead",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 10,
                            "default_sets": 3,
                            "default_duration": "30 seconds"
                        },
                        {
                            "id": "ft2",
                            "short_name": "Cross Body Reach",
                            "full_name": "Cross Body Reaching Exercise",
                            "description": "Reach across body to opposite side",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 10,
                            "default_sets": 3,
                            "default_duration": "25 seconds"
                        }
                    ]
                },
                "endurance_training": {
                    "name": "Endurance Training Program",
                    "exercises": [
                        {
                            "id": "et1",
                            "short_name": "Sustained Hold",
                            "full_name": "Sustained Position Hold",
                            "description": "Hold arm in position for extended time",
                            "youtube_url": "https://www.youtube.com/watch?v=BAOdoV7jQVo&list=RDBAOdoV7jQVo&start_radio=1",
                            "default_reps": 3,
                            "default_sets": 3,
                            "default_duration": "45 seconds"
                        }
                    ]
                }
            }
        }
    }

    exprTrackRecord = {
    "day0": [
        {"devicesteup": False},
        {"Demo": False}
    ],
    "day1": [
        {"Assessment": False},
        {"ActiGraph watches": False}
    ],
    "day2": [
        {"ADL(printOuts)": False}
    ],
    "day3": [
        {"Exercise Video Time Upload": False}
    ],
    "day15": [
        {"watches swap": False},
        {"exercise Revision": False},
        {"Exercise Video Time Upload": False}
    ],
    "day29": [
        {"Taking Back Device": False},
        {"Actigraph watches": False}
    ]
    }
    # Control Group Exercise Timing
    EXERCISE_TIMING_FOLDER = "start_and_end_time_for_exercise_pattern"
    VCG_TIMING_FILE = "vcg_timing.json"
    ADL_TIMING_FILE = "adl_timing.json"
    
    # Time Records (separate file for all time records per patient)
    TIME_RECORDS_FOLDER = "time_records"
    TIME_RECORDS_FILE = "time_records.json"
    
    # ADL Exercise Library
    ADL_EXERCISE_LIBRARY = {
        "basic_adl": {
            "name": "Basic Daily Activities",
            "exercises": [
                {
                    "id": "adl1",
                    "short_name": "Brushing Hair",
                    "full_name": "Hair Brushing Exercise",
                    "description": "Simulate brushing hair with affected arm",
                    "youtube_url": "https://youtube.com/adl1",
                    "default_reps": 10,
                    "default_sets": 3,
                    "default_duration": "30 seconds",
                    "instructions": "Hold brush and perform brushing motion"
                },
                {
                    "id": "adl2",
                    "short_name": "Drinking from Cup",
                    "full_name": "Cup Drinking Exercise",
                    "description": "Lift cup to mouth and simulate drinking",
                    "youtube_url": "https://youtube.com/adl2",
                    "default_reps": 10,
                    "default_sets": 3,
                    "default_duration": "20 seconds",
                    "instructions": "Lift cup to mouth, hold for 2 seconds, lower"
                },
                {
                    "id": "adl3",
                    "short_name": "Eating with Utensils",
                    "full_name": "Utensil Use Exercise",
                    "description": "Practice using fork/spoon",
                    "youtube_url": "https://youtube.com/adl3",
                    "default_reps": 15,
                    "default_sets": 2,
                    "default_duration": "25 seconds",
                    "instructions": "Scoop and bring to mouth motion"
                }
            ]
        },
        "reaching_adl": {
            "name": "Reaching Activities",
            "exercises": [
                {
                    "id": "adl4",
                    "short_name": "Reaching High Shelf",
                    "full_name": "Overhead Reaching",
                    "description": "Reach for objects on high shelf",
                    "youtube_url": "https://youtube.com/adl4",
                    "default_reps": 8,
                    "default_sets": 3,
                    "default_duration": "30 seconds",
                    "instructions": "Extend arm overhead to reach object"
                },
                {
                    "id": "adl5",
                    "short_name": "Opening Door",
                    "full_name": "Door Opening Exercise",
                    "description": "Simulate opening a door",
                    "youtube_url": "https://youtube.com/adl5",
                    "default_reps": 10,
                    "default_sets": 3,
                    "default_duration": "15 seconds",
                    "instructions": "Grasp and turn door handle motion"
                }
            ]
        },
        "fine_motor": {
            "name": "Fine Motor Activities",
            "exercises": [
                {
                    "id": "adl6",
                    "short_name": "Buttoning",
                    "full_name": "Buttoning Exercise",
                    "description": "Practice buttoning and unbuttoning",
                    "youtube_url": "https://youtube.com/adl6",
                    "default_reps": 5,
                    "default_sets": 3,
                    "default_duration": "45 seconds",
                    "instructions": "Button and unbutton practice"
                },
                {
                    "id": "adl7",
                    "short_name": "Writing",
                    "full_name": "Writing Exercise",
                    "description": "Practice writing or drawing",
                    "youtube_url": "https://youtube.com/adl7",
                    "default_reps": 5,
                    "default_sets": 2,
                    "default_duration": "60 seconds",
                    "instructions": "Write name or draw simple shapes"
                },
                {
                    "id": "adl8",
                    "short_name": "Using Phone",
                    "full_name": "Phone Use Exercise",
                    "description": "Practice using smartphone",
                    "youtube_url": "https://youtube.com/adl8",
                    "default_reps": 10,
                    "default_sets": 3,
                    "default_duration": "20 seconds",
                    "instructions": "Touch screen and swipe motions"
                }
            ]
        }
    }
    
    # Track records for control group
    ctrlTrackRecord = {
        "day1": [
            {"ActiGraph watches": False},
            {"ADL Exercise Prescription": False}
        ],
        "day2": [
            {"Exercise PrintOuts": False}
        ],
        "day3": [
            {"Exercise Video Time Upload": False},
            {"Exercise Timing Recording": False}  # New: Exercise timing starts
        ],
        "day15": [
            {"watches swap": False},
            {"exercise Revision": False},
            {"Exercise Video Time Upload": False},
            {"Exercise Timing Recording": False}  # New: Exercise timing opens again
        ],
        "day29": [
            {"Taking Back Device": False}
        ]
    }
    
    # Exit questionnaire template
    EXIT_QUESTIONNAIRE_FIELDS = [
        "patient_id",
        "discontinue_date",
        "reason_for_discontinuation",
        "adverse_events_occurred",
        "adverse_events_description",
        "satisfaction_rating",
        "comme"
        "nts"
    ]