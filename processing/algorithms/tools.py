"""
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = '3liz'
__date__ = '2019-02-15'
__copyright__ = '(C) 2019 by 3liz'

from qgis.PyQt.QtCore import QCoreApplication
from db_manager.db_plugins.plugin import BaseError
from db_manager.db_plugins import createDbPlugin
from db_manager.db_plugins.postgis.connector import PostGisDBConnector
import os, subprocess
from platform import system as psys

from qgis.core import (
    QgsExpressionContextUtils
)
import netrc
def tr(string):
    return QCoreApplication.translate('Processing', string)

def check_internet():
    # return True
    import requests
    # url='https://www.google.com/'
    url='https://www.3liz.com/images/flavicon.png'
    timeout=5
    try:
        _ = requests.get(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        return False

def getUriFromConnectionName(connection_name, must_connect=True):

    # Create plugin class and try to connect
    status = True
    uri = None
    error_message = ''
    connection = None
    try:
        dbpluginclass = createDbPlugin( 'postgis', connection_name )
        connection = dbpluginclass.connect()
    except BaseError as e:
        status = False
        error_message = e.msg
    except:
        status = False
        error_message = tr('Cannot connect to database with') + ' %s' % connection_name

    if not connection and must_connect:
        return status, uri, error_message

    db = dbpluginclass.database()
    if not db:
        status = False
        error_message = tr('Unable to get database from connection')
        return status, uri, error_message

    uri = db.uri()
    return status, uri, ''

def fetchDataFromSqlQuery(connection_name, sql):

    header = None
    data = []
    header = []
    rowCount = 0
    error_message = None
    connection = None
    ok = True

    # Get URI
    status, uri, error_message = getUriFromConnectionName(connection_name)

    if not uri:
        ok = False
        return header, data, rowCount, ok, error_message
    try:
        connector = PostGisDBConnector(uri)
    except:
        error_message = tr('Cannot connect to database')
        ok = False
        return header, data, rowCount, ok, error_message

    c = None
    ok = True
    #print "run query"
    try:
        c = connector._execute(None,str(sql))
        data = []
        header = connector._get_cursor_columns(c)
        if header == None:
            header = []
        if len(header) > 0:
            data = connector._fetchall(c)
        rowCount = c.rowcount
        if rowCount == -1:
            rowCount = len(data)

    except BaseError as e:
        ok = False
        error_message = e.msg
        return header, data, rowCount, ok, error_message
    finally:
        if c:
            c.close()
            del c

    # Log errors
    if not ok:
        error_message = tr('Unknown error occured while fetching data')
        return header, data, rowCount, ok, error_message
        print(error_message)
        print(sql)

    return header, data, rowCount, ok, error_message


def validateTimestamp(timestamp_text):
    from dateutil.parser import parse
    valid = True
    msg = ''
    try:
        parse(timestamp_text)
    except ValueError as e:
        valid = False
        msg = str(e)
    return valid, msg

def getVersionInteger(f):
    '''
    Transform "0.1.2" into "000102"
    Transform "10.9.12" into "100912"
    to allow comparing versions
    and sorting the upgrade files
    '''
    return ''.join([a.zfill(2) for a in f.strip().split('.')])


def run_command(cmd, myenv, feedback):
    '''
    Run any command using subprocess
    '''
    import re
    stop_words = ['warning']
    pattern = re.compile('|'.join(r'\b{}\b'.format(word) for word in stop_words), re.IGNORECASE)
    process = subprocess.Popen(
        " ".join(cmd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=myenv
    )
    for line in process.stdout:
        try:
            output = "{}".format(line.rstrip().decode("utf-8"))
        except:
            output = "{}".format(line.rstrip())
        if not pattern.search(output):
            print(output)
        if output == '' and process.poll() is not None:
            break
        if output:
            feedback.pushInfo(output)
    rc = process.poll()
    return rc

def check_lizsync_installation_status(connection_name, test_list=['structure', 'server id', 'uid columns', 'audit triggers'], schemas='test'):
    '''
    Checks if the central database
    has been initialized with Lizsync tools
    '''
    tests = {}
    global_status = True

    schemas = [
        "'{0}'".format(a.strip())
        for a in schemas.split(',')
        if a.strip() not in ( 'public', 'lizsync', 'audit')
    ]
    schemas_sql =  ', '.join(schemas)

    # Check metadata table
    if 'structure' in test_list:
        test = {'status': True, 'message': tr('Lizsync structure has been installed')}
        sql = ''
        sql+= " SELECT t.table_schema, t.table_name"
        sql+= " FROM information_schema.tables AS t"
        sql+= " WHERE t.table_schema = 'lizsync'"
        sql+= " AND t.table_name = 'server_metadata'"

        header, data, rowCount, ok, error_message = fetchDataFromSqlQuery(connection_name, sql)
        if ok:
            if rowCount != 1:
                global_status = False
                message = tr('The table lizsync.metadata has not been found')
                test['status'] = False
                test['message'] = message
        else:
            global_status = False
            test['status'] = False
            test['message'] = error_message
        tests['structure'] = test

    # Check server id
    if 'server id' in test_list:
        test = {'status': True, 'message': tr('Server id is not empty')}
        sql = ''
        sql+= " SELECT server_id FROM lizsync.server_metadata LIMIT 1"
        status = False
        header, data, rowCount, ok, error_message = fetchDataFromSqlQuery(connection_name, sql)
        if ok:
            if rowCount != 1:
                global_status = False
                message = tr('The server id in lizsync.metadata is not set')
                test['status'] = False
                test['message'] = message
        else:
            global_status = False
            test['status'] = False
            test['message'] = error_message
        tests['server id'] = test

    # Get missing uid columns
    if 'uid columns' in test_list:
        test = {'status': True, 'message': tr('No missing uid columns')}
        sql = ''
        sql+= " SELECT t.table_schema, t.table_name, (c.column_name IS NOT NULL) AS ok"
        sql+= " FROM information_schema.tables AS t"
        sql+= " LEFT JOIN information_schema.columns c"
        sql+= "     ON True"
        sql+= "     AND c.table_schema = t.table_schema"
        sql+= "     AND c.table_name = t.table_name"
        sql+= "     AND c.column_name = 'uid'"
        sql+= " WHERE TRUE"
        sql+= " AND t.table_schema IN ( {0} )"
        sql+= " AND t.table_type = 'BASE TABLE'"
        sql+= " AND c.column_name IS NULL"
        sql+= " ORDER BY t.table_schema, t.table_name"
        sqlc = sql.format(
            schemas_sql
        )
        header, data, rowCount, ok, error_message = fetchDataFromSqlQuery(connection_name, sqlc)
        missing = []
        if ok:
            for a in data:
                missing.append('"{0}"."{1}"'.format(a[0], a[1]))
        if missing:
            global_status = False
            message = tr('Some tables do not have the required uid column')
            message+= '\n{0}'.format(',\n '.join(missing))
            test['status'] = False
            test['message'] = message
        tests['uid columns'] = test


    # Check missing audit triggers
    if 'audit triggers' in test_list:
        test = {'status': True, 'message': tr('No missing audit triggers')}
        sql = ''
        sql+= " SELECT table_schema, table_name"
        sql+= " FROM information_schema.tables"
        sql+= " WHERE True"
        sql+= " AND table_schema IN ( {0} )"
        sql+= " AND table_type = 'BASE TABLE'"
        sql+= " AND (quote_ident(table_schema) || '.' || quote_ident(table_name))::text NOT IN ("
        sql+= "     SELECT (tgrelid::regclass)::text"
        sql+= "     FROM pg_trigger"
        sql+= "     WHERE TRUE"
        sql+= "     AND tgname LIKE 'audit_trigger_%'"
        sql+= " )"
        sqlc = sql.format(
            schemas_sql
        )
        status = False
        header, data, rowCount, ok, error_message = fetchDataFromSqlQuery(connection_name, sqlc)
        missing = []
        if ok:
            if rowCount > 0:
                for a in data:
                    missing.append('"{0}"."{1}"'.format(a[0], a[1]))
                global_status = False
                message = tr('Some tables are not monitored by the audit trigger tool')
                message+= ':\n{0}'.format(',\n '.join(missing))
                test['status'] = False
                test['message'] = message
        else:
            global_status = False
            test['status'] = False
            test['message'] = error_message

        tests['audit triggers'] = test

    return global_status, tests


def checkFtpBinary():
    # Check WinSCP path contains binary
    test = False

    # Windows : search for WinSCP
    if psys().lower().startswith('win'):
        test_path = QgsExpressionContextUtils.globalScope().variable('lizsync_winscp_binary_path')
        test_bin = 'WinSCP.com'
        error_message = 'WinSCP binary has not been found in specified path'
        test = True

    # Linux : search for lftp
    if psys().lower().startswith('linux'):
        test_path = '/usr/bin/'
        test_bin = 'lftp'
        error_message = 'LFTP binary has not been found in your system'
        test = True

    # Compute full path to test
    ftp_bin = os.path.join(
        test_path,
        test_bin
    )

    # Run test
    if test and not os.path.isfile(ftp_bin):
        return False, tr(error_message)
    if not test:
        return False, tr('No FTP binary has been found in your system')
    return True, tr('FTP Binary has been found in your system')

def ftp_sync(ftphost, ftpport, ftpuser, localdir, ftpdir, direction, excludedirs, feedback):

    # LINUX : USE lftp command line
    if psys().lower().startswith('linux'):
        try:
            cmd = []
            cmd.append('lftp')
            cmd.append('ftp://{0}@{1}:{2}'.format(ftpuser, ftphost, ftpport))
            cmd.append('-e')
            cmd.append('"')
            cmd.append('set ftp:ssl-allow no; set ssl:verify-certificate no; ')
            cmd.append('mirror')
            if direction == 'to':
                cmd.append('-R')
            cmd.append('--verbose')
            cmd.append('--continue')
            cmd.append('--use-cache')
            # cmd.append('-e') # pour supprimer tout ce qui n'est pas sur le serveur
            for d in excludedirs.split(','):
                ed = d.strip().strip('/') + '/'
                if ed != '/':
                    cmd.append('-x %s' % ed)
            cmd.append('--ignore-time')
            # LFTP NEEDS TO PUT
            # * from -> ftpdir (remote FTP server) BEFORE
            # * to (-R) -> localdir (computer) BEFORE ftpdir (remote FTP server)
            if direction == 'to':
                cmd.append('{} {}'.format(localdir, ftpdir))
            else:
                cmd.append('{} {}'.format(ftpdir, localdir))

            cmd.append('; quit"')
            feedback.pushInfo('LFTP = %s' % ' '.join(cmd) )

            myenv = { **os.environ }
            run_command(cmd, myenv, feedback)

        except:
            m = tr('Error during FTP sync')
            return False, m
        finally:
            feedback.pushInfo(tr('FTP sync done'))

    # WINDOWS : USE WinSCP.com tool
    elif psys().lower().startswith('win'):
        try:
            auth = netrc.netrc().authenticators(ftphost)
            if auth is not None:
                ftplogin, account, ftppass = auth
        except (netrc.NetrcParseError, IOError):
            m = self.tr('Could not retrieve password from ~/.netrc file')
            return False, m
        if not ftppass:
            m = self.tr('Could not retrieve password from ~/.netrc file or is empty')
            return False, m
        try:
            cmd = []
            winscp_bin = os.path.join(
                QgsExpressionContextUtils.globalScope().variable('lizsync_winscp_binary_path'),
                'WinSCP.com'
            ).replace('\\','/')
            cmd.append('"' + winscp_bin + '"')
            cmd.append('/ini=nul')
            cmd.append('/console')
            cmd.append('/command')
            cmd.append('"option batch off"')
            cmd.append('"option transfer binary"')
            cmd.append('"option confirm off"')
            cmd.append('"open ftp://{}:{}@{}:{}"'.format(ftpuser, ftppass, ftphost, ftpport))
            cmd.append('"')
            cmd.append('synchronize')
            way = 'local'
            if direction == 'to':
                way = 'remote'
            cmd.append(way)
            # WINSCP NEED TO ALWAYS HAVE local directory (computer) BEFORE FTP server remote directory
            cmd.append(
                '{} {}'.format(
                    localdir,
                    ftpdir
                )
            )
            cmd.append('-mirror')
            # cmd.append('-delete') # to delete "to" side files not present in the "from" side
            cmd.append('-criteria=time')
            cmd.append('-resumesupport=on')
            ex = []
            for d in excludedirs.split(','):
                ed = d.strip().strip('/') + '/'
                if ed != '/':
                    # For directory, no need to put * after.
                    # Just use the / at the end, for example: data/
                    ex.append('%s' % ed)
            if ex:
                # | 2010*; 2011*
                # double '""' needed because it's inside already quoted synchronize subcommand
                cmd.append('-filemask=""|' + ';'.join(ex) + '""')
            cmd.append('"')

            cmd.append('"close"')
            cmd.append('"exit"')

            infomsg = 'WinSCP = %s' % ' '.join(cmd)
            feedback.pushInfo(
                infomsg.replace(
                    ':{}@'.format(ftppass),
                    ':********@'
                )
            )

            myenv = { **os.environ }
            run_command(cmd, myenv, feedback)

        except:
            m = tr('Error during FTP sync')
            return False, m
        finally:
            feedback.pushInfo(tr('FTP sync done'))

    return True, 'Success'



def pg_dump(feedback, postgresql_binary_path, connection_name, output_file_name, schemas, additionnal_parameters=[]):

    messages = []
    status = False

    # Check binary
    pgbin = 'pg_dump'
    if psys().lower().startswith('win'):
        pgbin+= '.exe'
    pgbin = os.path.join(
        postgresql_binary_path,
        pgbin
    )
    if not os.path.isfile(pgbin):
        messages.append(tr('PostgreSQL pg_dump tool cannot be found in specified path'))
        return False, messages

    # Get connection parameters
    status, uri, error_message = getUriFromConnectionName(connection_name)
    if not uri:
        messages.append(tr('Error getting database connection information'))
        return status, messages

    # Create pg_dump command
    if uri.service():
        cmdo = [
            'service={0}'.format(uri.service())
        ]
    else:
        cmdo = [
            '-h {0}'.format(uri.host()),
            '-p {0}'.format(uri.port()),
            '-d {0}'.format(uri.database()),
            '-U {0}'.format(uri.username()),
        ]
    # Escape pgbin for Windows
    if psys().lower().startswith('win'):
        pgbin = '"' + pgbin + '"'
    cmd = [
        pgbin
    ] + cmdo + [
        '--no-acl',
        '--no-owner',
        '-Fp',
        '-f {0}'.format(output_file_name)
    ]

    # Add given schemas
    for s in schemas:
        cmd.append('-n {0}'.format(s))

    # Add additionnal parameters
    if additionnal_parameters:
        cmd = cmd + additionnal_parameters

    # Run command
    # print(" ".join(cmd))
    try:
        # messages.append('PG_DUMP = %s' % ' '.join(cmd) )
        # Add password if needed
        myenv = { **os.environ }
        if not uri.service():
            myenv = {**{'PGPASSWORD': uri.password()}, **os.environ }
        run_command(cmd, myenv, feedback)

        # subprocess.run(
            # " ".join(cmd),
            # shell=True,
            # env=myenv
        # )
        status = True
        messages.append(tr('Database has been successfull dumped') + ' into {0}'.format(output_file_name))
    except:
        status = False
        messages.append(tr('Error dumping database') + ' into {0}'.format(output_file_name))

    return status, messages


def setQgisProjectOffline(qgis_directory, connection_name_central, connection_name_clone, feedback):

    # Get uri from connection names
    status_central, uri_central, error_message_central = getUriFromConnectionName(connection_name_central)
    status_clone, uri_clone, error_message_clone = getUriFromConnectionName(connection_name_clone)
    if not status_central:
        m = error_message_central
        return False, m
    if not status_clone:
        m = error_message_clone
        return False, m

    uris = {
        'central': {'uri': uri_central},
        'clone'  : {'uri': uri_clone}
    }
    for a in ('central', 'clone'):
        uri = uris[a]['uri']
        if uri.service():
            uris[a]['info'] = {
                'service': uri.service(),
                'string': "service='%s'" % uri.service()
            }
        else:
            uris[a]['info'] = {
                'host': uri.host(),
                'port': uri.port(),
                'dbname': uri.database(),
                'user': uri.username(),
                'password': uri.password(),
                'string': "dbname='{}' host={} port={} user='{}' password='{}'".format(
                    uri.database(),
                    uri.host(),
                    uri.port(),
                    uri.username(),
                    uri.password()
                )
            }
    dbitems = {
        'service': "service='{}'",
        'dbname': "dbname='{}'",
        'host': "host={}",
        'port': "port={}",
        'user': "user='{}'",
        'password': "password='{}'"
    }
    # First loop to create modified version of QGIS projects (with added .xml extension)
    for filename in os.listdir(qgis_directory):
        if filename.endswith(".qgs"):
            qf = os.path.join(qgis_directory, filename)
            feedback.pushInfo(tr('Process QGIS project file') + ' %s' % qf)

            # Store QGIS project content in memory
            with open(qf, 'rt') as f:
                file_str = f.read()

            # Replace needed data
            # Loop through connection parameters and replace
            for k, v in dbitems.items():
                if k in uris['central']['info'] and k in uris['clone']['info']:
                    stext = v.format(uris['central']['info'][k])
                    rtext = v.format(uris['clone']['info'][k])
                    if stext in file_str:
                        print(stext)
                        print(rtext)
                        file_str = file_str.replace(stext, rtext)

            # to improve
            # alway replace user by clone local user
            # needed if there are multiple user stored in the qgis project for the same server
            # because one of them can be different from the central connection name user
            import re
            replaceAllUsers = True
            if replaceAllUsers:
                regex = re.compile(r"user='[A_Za-z_]+'", re.IGNORECASE)
                rtext = dbitems['user'].format(
                    uris['clone']['info']['user']
                )
                file_str = regex.sub(
                    rtext,
                    file_str
                )

            # Write content back to project file
            qf2 = os.path.join(qgis_directory, filename + '.xml')
            feedback.pushInfo(tr('Write new QGIS project with XML extension') + ' %s' % filename + '.xml' )
            with open(qf2, "w") as f:
                f.write(file_str)

    # Remove old QGIS projects
    for filename in os.listdir(qgis_directory):
        if filename.endswith(".qgs"):
            qf = os.path.join(qgis_directory, filename)
            feedback.pushInfo(tr('Remove old QGIS project') + ' %s' % filename )
            os.remove(qf)

    # Rename new QGIS projects
    for filename in os.listdir(qgis_directory):
        if filename.endswith(".qgs.xml"):
            qf = os.path.join(qgis_directory, filename)
            feedback.pushInfo(tr('Rename new QGIS project to *.qgs') + ' %s' % filename )
            os.rename(qf, qf.replace('.qgs.xml', '.qgs'))

    return True, 'Success'

def returnError(output, msg, feedback):
    """
    Report errors
    """
    status = 0
    output_string = 'OUTPUT_STRING'
    feedback.reportError(msg)
    if output_string in output:
        output[output_string] = msg
    # raise Exception(msg)
    # commented because it does not work with py-qgis-wps

    return output
