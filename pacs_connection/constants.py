
COLS = ["PatientName", "PatientID", "StudyInstanceUID", "SeriesInstanceUID", "StudyDate", "StudyTime", "AccessionNumber", "Modality", "PatientBirthDate", "PatientSex", "PatientAge", "IssuerOfPatientID", "Retrieve AE Title", "StudyDescription"]
INV_PORT = 5050
INV_AET = 'INVESALIUS'
INV_HOST = 'localhost'
READ_MAPPER = {
    'Patient ID' : 'PatientID',
    'Patient Name' : 'PatientName',
    'StudyInstanceUID' : 'StudyInstanceUID',
}
CONFIG_FILE = 'pacs_connection\config.json'

