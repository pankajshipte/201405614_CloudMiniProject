import libvirt
from flask import *
import uuid
import json
import sqlite3
import sys
import os

app = Flask(__name__)
DATABASE = 'Database.db'
if len(sys.argv) == 4:
    flavor_file = sys.argv[3]
    pm_file = sys.argv[1]
    image_file = sys.argv[2]
else:
    print("Incorrect Arguments!!!\n")
    exit()

# '/home/samarth/myproject/input/flavor_file'
with open(flavor_file) as instance_file:
    instance = json.load(instance_file)

dbcon = sqlite3.connect(DATABASE)
# '/home/samarth/myproject/input/pm_file'
with open(pm_file, 'r') as ips_file:
    for line in ips_file:
        line = line.strip()
        if line:
            cur = dbcon.execute('SELECT pm_id FROM pm_table WHERE ip = ?', [line])
            ip = cur.fetchone()
            cur.close()
            if ip is None:
                dbcon.execute('INSERT INTO pm_table (ip) VALUES (?)', [line])
                dbcon.commit()

# '/home/samarth/myproject/input/image_file'
with open(image_file, 'r') as img_file:
    for line in img_file:
        line = line.strip()
        if line:
            cur = dbcon.execute('SELECT img_id FROM img_table WHERE path = ?', [line])
            imgid = cur.fetchone()
            cur.close()
            if imgid is None:
                dbcon.execute('INSERT INTO img_table (path) VALUES (?)', [line])
                dbcon.commit()

dbcon.close()


@app.before_request
def before_request():
    g.db = sqlite3.connect(DATABASE)


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


@app.route('/', methods=['GET', 'POST'])
def welcome_page():
    return render_template('welcome.html')


@app.route('/vm/create', methods=['GET', 'POST'])
def create_vm():
    name = request.args.get('name')  # request.form('name')
    if not name:
        return render_template('response.html', result=json.dumps({"status": 0}))
    instance_type = request.args.get('instance_type')  # request.args.get('instance_type')
    if not instance_type:
        return render_template('response.html', result=json.dumps({"status": 0}))
    instance_type = int(instance_type)
    imgid = request.args.get('image_id')  # request.args.get('image_id')
    if not imgid:
        return render_template('response.html', result=json.dumps({"status": 0}))
    imgid = int(imgid)
    flag = False
    for i in instance['types']:
        if i['tid'] == instance_type:
            ram = i["ram"]
            cpu = i["cpu"]
            disk = i["disk"]
            flag = True
            break

    if not flag:
        ram = 600
        cpu = 1
        disk = 1

    for ip in g.db.execute('select pm_id, ip from pm_table'):
        connstr = "qemu+ssh://" + str(ip[1]) + "/system"
        conn = libvirt.open(connstr)
        pmid = ip[0]

        sysInfo = conn.getInfo()
        totMem = int(sysInfo[1])
        totCpu = int(sysInfo[2])
        totDisc = 250
        exists = True
        try:
            vm = conn.lookupByName(name)
        except libvirt.libvirtError:
            exists = False

        if exists:
            return render_template('response.html', result=json.dumps({"status": 0}))
        usedCpu = 0
        usedMem = 0
        usedDisc = 0
        for vmItr in g.db.execute('select * from vm_table where pm_id = ?', [pmid]):
            usedCpu = usedCpu + vmItr[6]
            usedMem = usedMem + vmItr[5]
            usedDisc = usedDisc + vmItr[7]

        if (totCpu - usedCpu) >= cpu and (totMem - usedMem) >= ram and (totDisc - usedDisc) >= disk:
            uid = uuid.uuid1()
            cur = g.db.execute('select path from img_table where img_id = ?', [imgid])
            img = cur.fetchone()
            cur.close()
            if img is None:
                return render_template('response.html', result=json.dumps({"status": 0}))
            username = str(ip[1]).split("@")
            destPath = "/home/" + username[0] + "/" + name + ".img"
            os.system("scp " + str(img[0]) +" "+ str(ip[1]) + ":" + destPath)
            xmlstr = open("xml/template.xml")
            xml = xmlstr.read()

            xml = xml.replace("$name", name)
            xml = xml.replace("$uuid", str(uid))
            xml = xml.replace("$vram", str(int(ram * 10.24)))
            xml = xml.replace("$mem", str(ram * 1024))
            xml = xml.replace("$cpu", str(cpu))
            xml = xml.replace("$disk", str(disk))
            xml = xml.replace("$img", destPath)
            # print xml
            conn.defineXML(xml)

            try:
                vm1 = conn.lookupByName(name)
            except libvirt.libvirtError:
                return render_template('response.html', result=json.dumps({"vmid": 0}))

            vm1.create()
            g.db.execute(
                'insert into vm_table (pk, name, instance_type, pm_id, img_id, used_memory, used_cpu, used_disk) values (?, ?, ?, ?, ?, ?, ?, ?)',
                [vm1.ID(), name, instance_type, pmid, imgid, ram, cpu, disk])
            g.db.commit()
            return render_template('response.html', result=json.dumps({"vmid": vm1.ID()}))
        else:
            continue
    return render_template('response.html', result=json.dumps({"status": 0}))


@app.route('/vm/query', methods=['GET', 'POST'])
def query_vm():
    vmid = request.args.get('vmid')
    if not vmid:
        return render_template('response.html', result=json.dumps({"status": 0}))
    vmid = int(vmid)
    cur = g.db.execute('select pk, name, instance_type, pm_id from vm_table where pk = ?', [vmid])
    vmDetalis = cur.fetchone()
    cur.close()
    if vmDetalis is None:
        return render_template('response.html', result=json.dumps({"status": 0}))
    else:
        result = json.dumps({'vmid':vmDetalis[0], 'name':vmDetalis[1], 'instance_type':vmDetalis[2], 'pmid':vmDetalis[3]})
        return render_template('response.html', result=result)


@app.route('/vm/destroy', methods=['GET', 'POST'])
def destroy_vm():
    vmid = request.args.get('vmid')
    if not vmid:
        return render_template('response.html', result=json.dumps({'status': 0}))
    vmid = int(vmid)
    cur = g.db.execute('select ip from pm_table where pm_id = (select pm_id from vm_table where pk = ?)', [vmid])
    ip = cur.fetchone()
    cur.close()
    if ip is None:
        return render_template('response.html', result=json.dumps({"status": 0}))
    connstr = "qemu+tcp://" + str(ip[0]) + "/system"
    conn = libvirt.open(connstr)
    try:
        vm = conn.lookupByID(vmid)
        vm.destroy()
        vm.undefine()
        g.db.execute('delete from vm_table where pk = ?', [vmid])
        g.db.commit()
        return render_template('response.html', result=json.dumps({"status": 1}))
    except libvirt.libvirtError:
        return render_template('response.html', result=json.dumps({"status": 0}))  # jsonify(status=0)


@app.route('/vm/types', methods=['GET', 'POST'])
def vm_types():
    return render_template('response.html', result=instance)


@app.route('/pm/list', methods=['GET', 'POST'])
def list_pm():
    pmDict = []
    flag = False
    for pmItr in g.db.execute('select pm_id from pm_table'):
        pmDict.append(pmItr[0])
        flag = True
    if not flag:
        return render_template('response.html', result=json.dumps({"status": 0}))
    return render_template('response.html', result=json.dumps({"pmid": pmDict}))


@app.route('/pm/listvms', methods=['GET', 'POST'])
def list_vm():
    pmid = request.args.get('pmid')
    if not pmid:
        return render_template('response.html', result=json.dumps({"status": 0}))
    pmid = int(pmid)
    vmDict = []
    cur = g.db.execute('select ip from pm_table where pm_id = ?', [pmid])
    ip = cur.fetchone()
    cur.close()
    if ip is None:
        return render_template('response.html', result=json.dumps({"status": 0}))
    for vmItr in g.db.execute('select pk from vm_table where pm_id = ?', [pmid]):
        vmDict.append(vmItr[0])
    return render_template('response.html', result=json.dumps({"vmids": vmDict}))


@app.route('/pm/query', methods=['GET', 'POST'])
def query_pm():
    pmid = request.args.get('pmid')
    if not pmid:
        return render_template('response.html', result=json.dumps({"status": 0}))
    pmid = int(pmid)
    usedCpu = 0
    usedMem = 0
    usedDisc = 0
    count = 0
    cur = g.db.execute('select ip from pm_table where pm_id = ?', [pmid])
    ip = cur.fetchone()
    cur.close()
    if ip is None:
        return render_template('response.html', result=json.dumps({"status": 0}))

    connstr = "qemu+tcp://" + str(ip[0]) + "/system"
    conn = libvirt.open(connstr)
    sysInfo = conn.getInfo()
    totMem = int(sysInfo[1])
    totCpu = int(sysInfo[2])
    totDisc = 250
    capacity = {"cpu": totCpu, "ram": totMem, "disc": totDisc}

    for vmItr in g.db.execute('select * from vm_table where pm_id = ?', [pmid]):
        usedCpu = usedCpu + vmItr[6]
        usedMem = usedMem + vmItr[5]
        usedDisc = usedDisc + vmItr[7]
        count = count + 1

    free = {"cpu": totCpu - usedCpu, "ram": totMem - usedMem, "disc": totDisc - usedDisc}
    return render_template('response.html', result=json.dumps({'pmid':pmid, 'capacity':capacity, 'free':free, 'vms':count}))


@app.route('/image/list', methods=['GET', 'POST'])
def list_image():
    imgArray = []
    flag = False
    for imgItr in g.db.execute('select img_id, path from img_table'):
        image = {"id": imgItr[0], "name": imgItr[1]}
        imgArray.append(image)
        flag = True
    if not flag:
        return render_template('response.html', result=json.dumps({"status": 0}))
    return render_template('response.html', result=json.dumps({"images": imgArray}))

# ----------------------------------------------------------------------------------------------------------------------


@app.route('/volume/create', methods=['GET', 'POST'])
def Volume_Creation():
    name = request.args.get('name')
    if not name:
        return render_template('response.html', result=json.dumps({'status': 0}))
    size = request.args.get('size')
    if not size:
        return render_template('response.html', result=json.dumps({'status': 0}))

    for ip in g.db.execute('select pm_id, ip from pm_table'):
        connstr = "qemu+ssh://" + str(ip[1]) + "/system"
        conn = libvirt.open(connstr)
        pmid = ip[0]

        try:
            pool = conn.storagePoolLookupByName('mypool')
        except libvirt.libvirtError:
            username = str(ip[1]).split("@")
            destPath = "/home/" + username[0] + "/mypool/"
            uid = uuid.uuid1()

            xmlstr = open("xml/poolTemplate.xml")
            xml = xmlstr.read()

            xml = xml.replace("$uuid", str(uid))
            xml = xml.replace("$path", destPath)

            try:
                pool = conn.storagePoolDefineXML(xml, 0)
            except:
                continue
            pool.build()
            pool.create()
            pool.setAutostart(1)

        exists = True
        try:
            vol = pool.storageVolLookupByName(name)
        except libvirt.libvirtError:
            exists = False

        if exists:
            return render_template('response.html', result=json.dumps({"volumeid": 0}))


        username = str(ip[1]).split("@")
        destPath = "/home/" + username[0] + "/mypool/" + name

        xmlstr = open("xml/volumeTemplate.xml")
        xml = xmlstr.read()

        xml = xml.replace("$name", name)
        xml = xml.replace("$size", size)
        xml = xml.replace("$path", destPath)

        try:
            vol = pool.createXML(xml, 0)
        except libvirt.libvirtError:
            continue

        g.db.execute(
            'insert into vol_table (name, path, pm_id, attached, size) values (?, ?, ?, ?, ?)',
            [name, destPath, pmid, 0, size])
        g.db.commit()
        cur = g.db.execute('select vol_id from vol_table where name = ?', [name])
        vol_id = cur.fetchone()
        return render_template('response.html', result=json.dumps({"volumeid": vol_id[0]}))

    return render_template('response.html', result=json.dumps({"volumeid": 0}))



@app.route('/volume/destroy', methods=['GET', 'POST'])
def Volume_Destroy():
    vmid = request.args.get('volumeid')

    if not vmid:
        return render_template('response.html', result=json.dumps({'status': 0}))
    vmid = int(vmid)

    cur = g.db.execute('select ip from pm_table where pm_id = (select pm_id from vol_table where vol_id = ?)', [vmid])
    ip = cur.fetchone()
    cur.close()
    if ip is None:
        return render_template('response.html', result=json.dumps({"status": 0}))

    cur = g.db.execute('select attached from vol_table where vol_id = ?', [vmid])
    rec = cur.fetchone()
    attached = rec[0]
    cur.close()

    if attached != 0:
        return render_template('response.html', result=json.dumps({"status": 0}))

    connstr = "qemu+tcp://" + str(ip[0]) + "/system"
    conn = libvirt.open(connstr)
    try:
        cur = g.db.execute('select name from vol_table where vol_id = ?', [vmid])
        name = cur.fetchone()
        cur.close()
        pool = conn.storagePoolLookupByName('mypool')
        vol = pool.storageVolLookupByName(name[0])
        vol.wipe(0)
        vol.delete(0)
        g.db.execute('delete from vol_table where vol_id = ?', [vmid])
        g.db.commit()
        return render_template('response.html', result=json.dumps({"status": 1}))
    except libvirt.libvirtError:
        return render_template('response.html', result=json.dumps({"status": 0}))  # jsonify(status=0)


@app.route('/volume/attach', methods=['GET', 'POST'])
def Volume_Attach():
    vmid = request.args.get('vmid')
    volid = request.args.get('volumeid')
    if not vmid:
        return render_template('response.html', result=json.dumps({'status': 0}))
    if not volid:
        return render_template('response.html', result=json.dumps({'status': 0}))
    vmid = int(vmid)
    volid = int(volid)

    cur = g.db.execute('select ip from pm_table where pm_id = (select pm_id from vol_table where vol_id = ?)', [volid])
    ipVol = cur.fetchone()
    cur.close()
    if ipVol is None:
        return render_template('response.html', result=json.dumps({"status": 0}))

    cur = g.db.execute('select ip from pm_table where pm_id = (select pm_id from vm_table where pk = ?)', [vmid])
    ipvm = cur.fetchone()
    cur.close()
    if ipvm is None:
        return render_template('response.html', result=json.dumps({"status": 0}))

    cur = g.db.execute('select name, path, attached, size from vol_table where vol_id = ?', [volid])
    rec = cur.fetchone()
    name = rec[0]
    path = rec[1]
    attached = rec[2]
    size = rec[3]
    cur.close()

    cur = g.db.execute('select pm_id from vm_table where pk = ?', [vmid])
    pmid = cur.fetchone()
    cur.close()

    if attached == 1:
        return render_template('response.html', result=json.dumps({"status": 0}))

    if ipVol[0] == ipvm[0]:
        try:
            connstr = "qemu+tcp://" + str(ipvm[0]) + "/system"
            conn = libvirt.open(connstr)
            vm = conn.lookupByID(vmid)

            xmlstr = open("xml/diskTemplate.xml")
            xml = xmlstr.read()
            xml = xml.replace("$path", path)

            vm.attachDevice(xml)
            g.db.execute('update vol_table set attached=? where vol_id=?',
                [vmid, volid])
            g.db.commit()
            return render_template('response.html', result=json.dumps({"status": 1}))
        except libvirt.libvirtError:
                return render_template('response.html', result=json.dumps({"volumeid": 0}))
    else:
        connstr = "qemu+ssh://" + str(ipvm[0]) + "/system"
        conn = libvirt.open(connstr)

        try:
            pool = conn.storagePoolLookupByName('mypool')
        except libvirt.libvirtError:
            username = str(ip[1]).split("@")
            destPath = "/home/" + username[0] + "/mypool/"
            uid = uuid.uuid1()

            xmlstr = open("xml/poolTemplate.xml")
            xml = xmlstr.read()

            xml = xml.replace("$uuid", str(uid))
            xml = xml.replace("$path", destPath)

            try:
                pool = conn.storagePoolDefineXML(xml, 0)
            except:
                return render_template('response.html', result=json.dumps({"volumeid": 0}))

            pool.build()
            pool.create()
            pool.setAutostart(1)

        exists = True
        try:
            vol = pool.storageVolLookupByName(name)
        except libvirt.libvirtError:
            exists = False

        if not exists:
            username = str(ipvm[0]).split("@")
            destPath = "/home/" + username[0] + "/mypool/" + name

            xmlstr = open("xml/volumeTemplate.xml")
            xml = xmlstr.read()

            xml = xml.replace("$name", name)
            xml = xml.replace("$size", str(size))
            xml = xml.replace("$path", destPath)

            try:
                vol = pool.createXML(xml, 0)
            except libvirt.libvirtError:
                return render_template('response.html', result=json.dumps({"volumeid": 0}))

        try:
            vm = conn.lookupByID(vmid)
            xmlstr = open("xml/diskTemplate.xml")
            xml = xmlstr.read()
            xml = xml.replace("$path", path)
            vm.attachDevice(xml)
        except libvirt.libvirtError:
            return render_template('response.html', result=json.dumps({"volumeid": 0}))

        if not exists:
            connstr = "qemu+tcp://" + str(ipVol[0]) + "/system"
            conn = libvirt.open(connstr)
            pool = conn.storagePoolLookupByName('mypool')
            vol = pool.storageVolLookupByName(name[0])
            vol.wipe(0)
            vol.delete(0)

            g.db.execute('update vol_table set path=?, pm_id=?, attached=? where vol_id=?',
                [destPath, pmid, vmid, volid])
            g.db.commit()
        else:
            g.db.execute('update vol_table set attached=? where vol_id=?', [vmid, volid])
            g.db.commit()
        return render_template('response.html', result=json.dumps({"status": 1}))


@app.route('/volume/detach', methods=['GET', 'POST'])
def Volume_Detach():
    volid = request.args.get('volumeid')
    if not volid:
        return render_template('response.html', result=json.dumps({'status': 0}))
    volid = int(volid)

    cur = g.db.execute('select ip from pm_table where pm_id = (select pm_id from vol_table where vol_id = ?)', [volid])
    ipVol = cur.fetchone()
    cur.close()
    if ipVol is None:
        return render_template('response.html', result=json.dumps({"status": 0}))

    cur = g.db.execute('select name, path, attached, size from vol_table where vol_id = ?', [volid])
    rec = cur.fetchone()
    name = rec[0]
    path = rec[1]
    attached = rec[2]
    size = rec[3]
    cur.close()

    if attached == 0:
        return render_template('response.html', result=json.dumps({"status": 0}))
    try:
        connstr = "qemu+tcp://" + str(ipVol[0]) + "/system"
        conn = libvirt.open(connstr)
        vm = conn.lookupByID(attached)
        xmlstr = open("xml/diskTemplate.xml")
        xml = xmlstr.read()
        xml = xml.replace("$path", path)
        vm.detachDevice(xml)
        g.db.execute('update vol_table set attached=0 where vol_id=?', [volid])
        g.db.commit()
        return render_template('response.html', result=json.dumps({"status": 1}))
    except libvirt.libvirtError:
        return render_template('response.html', result=json.dumps({"status": 0}))


@app.route('/volume/query', methods=['GET', 'POST'])
def Volume_Query():
    volid = request.args.get('volumeid')
    if not volid:
        return render_template('response.html', result=json.dumps({'status': 0}))
    volid = int(volid)

    cur = g.db.execute('select ip from pm_table where pm_id = (select pm_id from vol_table where vol_id = ?)', [volid])
    ipVol = cur.fetchone()
    cur.close()
    if ipVol is None:
        return render_template('response.html', result=json.dumps({"error": "volumeid : "+ str(volid) +" does not exist"}))

    cur = g.db.execute('select name, path, attached, size from vol_table where vol_id = ?', [volid])
    rec = cur.fetchone()
    name = rec[0]
    path = rec[1]
    attached = rec[2]
    size = rec[3]
    cur.close()

    if attached == 0:
        return render_template('response.html', result=json.dumps({'volumeid':volid, 'name':name, 'size':size, 'status':"available"}))
    return render_template('response.html', result=json.dumps({'volumeid':volid, 'name':name, 'size':size, 'status':"attached", 'vmid':attached}))


@app.errorhandler(404)
def page_not_found(error):
    return render_template('response.html', result=json.dumps({"status": 0}))


if __name__ == '__main__':
    app.run(debug=True)
