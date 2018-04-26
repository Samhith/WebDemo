/*
Copyright 2015-2016 Carnegie Mellon University

you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/  
navigator.getUserMedia = navigator.getUserMedia ||
    navigator.webkitGetUserMedia ||
    (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) ?
        function(c, os, oe) {
            navigator.mediaDevices.getUserMedia(c).then(os,oe);
        } : null ||
    navigator.msGetUserMedia;

window.URL = window.URL ||
    window.webkitURL ||
    window.msURL ||
    window.mozURL;

// http://stackoverflow.com/questions/6524288
$.fn.pressEnter = function(fn) {

    return this.each(function() {
        $(this).bind('enterPress', fn);
        $(this).keyup(function(e){
            if(e.keyCode == 13)
            {
              $(this).trigger("enterPress");
            }
        })
    });
 };


function registerHbarsHelpers() {
    // http://stackoverflow.com/questions/8853396
    Handlebars.registerHelper('ifEq', function(v1, v2, options) {
        if(v1 === v2) {
            return options.fn(this);
        }
        return options.inverse(this);
    });
}

function sendFrameLoop() {
    if (socket == null || socket.readyState != socket.OPEN ||
        !vidReady || numNulls != defaultNumNulls) {
        return;
    }

    if (tok > 0) {
        var canvas = document.createElement('canvas');
        canvas.width = vid.width;
		
        canvas.height = vid.height;
        var cc = canvas.getContext('2d');
        cc.drawImage(vid, 0, 0, vid.width, vid.height);
        var apx = cc.getImageData(0, 0, vid.width, vid.height);
        var dataURL = canvas.toDataURL('image/jpeg', 0.6)
        var msg = {
            'type': 'FRAME',
            'dataURL': dataURL,
            'identity': defaultPerson,
            "ID": uniqueId
            };
        socket.send(JSON.stringify(msg));
        tok--;
    }
    setTimeout(function() {requestAnimFrame(sendFrameLoop)}, 250);
}
function submit_by_data(){
    var name = document.getElementById("name").value;
    var email = document.getElementById("email").value;
    var mobile = document.getElementById("number").value;
    var company = document.getElementById("company").value;
	if(name== "" || email == "" || mobile == "" || company == ""){
	  toastr.error('Please enter the details');
	  return false;
	}else{
	 
     var reg = /^([A-Za-z0-9_\-\.])+\@([A-Za-z0-9_\-\.])+\.([A-Za-z]{2,4})$/;
	 var mobilereg = /^[2-9]{2}[0-9]{8}$/;
       if (reg.test(email) == false) 
        {
            toastr.error('Invalid Email Address');
            return false;
        }else if(mobilereg.test(mobile) == false){
			toastr.error('Invalid Mobile Number');
            return false;
		}else{
			$('#pageMsgModal').modal('show');  
	  }
	
    }
}
function getPeopleInfoHtml() {
    var info = {'-1': 0};
    var len = people.length;
    for (var i = 0; i < len; i++) {
        info[i] = 0;
    }

    var len = images.length;
    for (var i = 0; i < len; i++) {
        id = images[i].identity;
        info[id] += 1;
    }

    var h = "<li><b>Unknown:</b> "+info['-1']+"</li>";
    var len = people.length;
    for (var i = 0; i < len; i++) {
        h += "<li><b>"+people[i]+":</b> "+info[i]+"</li>";
    }
    return h;
}

function redrawPeople() {
    var context = {people: people, images: images};
    $("#peopleTable").html(peopleTableTmpl(context));

    var context = {people: people};
    $("#defaultPersonDropdown").html(defaultPersonTmpl(context));

    $("#peopleInfo").html(getPeopleInfoHtml());
}

function getDataURLFromRGB(rgb) {
    var rgbLen = rgb.length;

    var canvas = $('<canvas/>').width(96).height(96)[0];
    var ctx = canvas.getContext("2d");
    var imageData = ctx.createImageData(96, 96);
    var data = imageData.data;
    var dLen = data.length;
    var i = 0, t = 0;

    for (; i < dLen; i +=4) {
        data[i] = rgb[t+2];
        data[i+1] = rgb[t+1];
        data[i+2] = rgb[t];
        data[i+3] = 255;
        t += 3;
    }
    ctx.putImageData(imageData, 0, 0);

    return canvas.toDataURL("image/png");
}

function updateRTT() {
    var diffs = [];
    for (var i = 5; i < defaultNumNulls; i++) {
        diffs.push(receivedTimes[i] - sentTimes[i]);
    }
    $("#rtt-"+socketName).html(
        jStat.mean(diffs).toFixed(2) + " ms (σ = " +
            jStat.stdev(diffs).toFixed(2) + ")"
    );
}

function sendState() {
    var msg = {
        'type': 'ALL_STATE',
        'images': images,
        'people': people,
        'training': training
    };
    socket.send(JSON.stringify(msg));
}

function createSocket(address, name) {

    socket = new WebSocket(address);
    socketName = name;
    socket.binaryType = "arraybuffer";
    socket.onopen = function() {
        $("#serverStatus").html("Connected to " + name);
        sentTimes = [];
        receivedTimes = [];
        tok = defaultTok;
        numNulls = 0
        numwarning =0;
        socket.send(JSON.stringify({'type': 'NULL'}));
        sentTimes.push(new Date());
    }
    socket.onmessage = function(e) {
		
		$('#submitbtn').attr('disabled',false);
        console.log(e);
        j = JSON.parse(e.data)
        if (j.type == "NULL") {
            receivedTimes.push(new Date());
            numNulls++;
            if (numNulls == defaultNumNulls) {
                updateRTT();
                sendState();
                sendFrameLoop();
            } else {
                socket.send(JSON.stringify({'type': 'NULL'}));
                sentTimes.push(new Date());
            }
        } else if (j.type == "PROCESSED") {
            tok++;
			
        }  else if(j.type == "STORED_PAGE2"){
            uniqueId = j.id;
            console.log(uniqueId);
            console.log("Calling page3");
            sessionStorage.setItem("uniqueId", uniqueId);
             tok=1;
            sendFrameLoop();
            loaded();			
           // window.open("page3.html");
        }  else if(j.type == "WARNING") {
			$('#submitbtn').attr('disabled',true);
            tok++;
			numwarning++;
			if(numwarning == 10){
				numwarning=0;
			  toastr.warning("Unable detect face");
			}
			if(numwarning == 10 && page3 == true){
			   timeout = timeout + 5000;
			  // timer.pause();
			}
            console.log(j.message)
        }  else if(j.type == "END_FACE_COLLECTION"){
            tok = -100;
            var UsrName = j.name;
            var mailID = j.mail;
            socket.send(JSON.stringify({'type': 'STOPPED_ACK',"name":UsrName,"mail":mailID}))
        } 
//		else if(j.type == "PAGE3"){
           // sendFrameLoop();
        //}
		else if (j.type == "NEW_IMAGE") {
            images.push({
                hash: j.hash,
                identity: j.identity,
                image: getDataURLFromRGB(j.content),
                representation: j.representation
            });
            redrawPeople();
        } else if (j.type == "IDENTITIES") {
            var h = "Last updated: " + (new Date()).toTimeString();
            h += "<ul>";
            var len = j.identities.length
            if (len > 0) {
                for (var i = 0; i < len; i++) {
                    var identity = "Unknown";
                    var idIdx = j.identities[i];
                    if (idIdx != -1) {
                        identity = people[idIdx];
                    }
                    h += "<li>" + identity + "</li>";
                }
            } else {
                h += "<li>Nobody detected.</li>";
            }
            h += "</ul>"
            $("#peopleInVideo").html(h);
        } else if (j.type == "ANNOTATED") {
            $("#detectedFaces").html(
                "<img src='" + j['content'] + "' width='430px'></img>"
            )
        } else if (j.type == "TSNE_DATA") {
            BootstrapDialog.show({
                message: "<img src='" + j['content'] + "' width='100%'></img>"
            });
        } else {
            console.log("Unrecognized message type: " + j.type);
        }
    }
    socket.onerror = function(e) {
        console.log("Error creating WebSocket connection to " + address);
        console.log(e);
    }
    socket.onclose = function(e) {
        if (e.target == socket) {
            $("#serverStatus").html("Disconnected.");
        }
    }
}

function umSuccess(stream) {
    var vid = document.getElementById('videoel');
    if (vid.mozCaptureStream) {
        vid.mozSrcObject = stream;
    } else {
        vid.src = (window.URL && window.URL.createObjectURL(stream)) ||
            stream;
    }
    vid.play();
    vidReady = true;
    sendFrameLoop();
}

function RegisterbtnOnClick(){
    if(socket != null){
        var msg = {
            'type': 'register_click',
            'val': 'clicked on register'
        };
        socket.send(JSON.stringify(msg));

    }
}



function addPersonCallback(el) {
    defaultPerson = people.length;
    var newPerson = "Clicked the button";
    if (newPerson == "") return;
    people.push(newPerson);
    $("#addPersonTxt").val("");

    if (socket != null) {
        var msg = {
            'type': 'ADD_PERSON',
            'val': newPerson
        };
        socket.send(JSON.stringify(msg));
    }
    redrawPeople();
}

function trainingChkCallback() {
    training = $("#trainingChk").prop('checked');
    if (training) {
        makeTabActive("tab-preview");
    } else {
        makeTabActive("tab-annotated");
    }
    if (socket != null) {
        var msg = {
            'type': 'TRAINING',
            'val': training
        };
        socket.send(JSON.stringify(msg));
    }
}

function viewTSNECallback(el) {
    if (socket != null) {
        var msg = {
            'type': 'REQ_TSNE',
            'people': people
        };
        socket.send(JSON.stringify(msg));
    }
}

function findImageByHash(hash) {
    var imgIdx = 0;
    var len = images.length;
    for (imgIdx = 0; imgIdx < len; imgIdx++) {
        if (images[imgIdx].hash == hash) {
            console.log("  + Image found.");
            return imgIdx;
        }
    }
    return -1;
}

function updateIdentity(hash, idx) {
    var imgIdx = findImageByHash(hash);
    if (imgIdx >= 0) {
        images[imgIdx].identity = idx;
        var msg = {
            'type': 'UPDATE_IDENTITY',
            'hash': hash,
            'idx': idx
        };
        socket.send(JSON.stringify(msg));
    }
}

function removeImage(hash) {
    console.log("Removing " + hash);
    var imgIdx = findImageByHash(hash);
    if (imgIdx >= 0) {
        images.splice(imgIdx, 1);
        redrawPeople();
        var msg = {
            'type': 'REMOVE_IMAGE',
            'hash': hash
        };
        socket.send(JSON.stringify(msg));
    }
}

function changeServerCallback() {
    $(this).addClass("active").siblings().removeClass("active");
    switch ($(this).html()) {
    case "Local":
        socket.close();
        redrawPeople();
        createSocket("wss:" + window.location.hostname + ":9000", "Local");
        break;
    case "CMU":
        socket.close();
        redrawPeople();
        createSocket("wss://facerec.cmusatyalab.org:9000", "CMU");
        break;
    case "AWS East":
        socket.close();
        redrawPeople();
        createSocket("wss://54.159.128.49:9000", "AWS-East");
        break;
    case "AWS West":
        socket.close();
        redrawPeople();
        createSocket("wss://54.188.234.61:9000", "AWS-West");
        break;
    default:
        alert("Unrecognized server: " + $(this.html()));
    }
}

  function loaded()
        {
            uniqueId = sessionStorage.getItem("uniqueId");
            toastr.info("This window will be closed after 30 seconds");
            window.setTimeout(CloseMe, timeout);
        }

  function CloseMe() 
        {
			tok=-100;
           // toastr.success("Saved your face successfully");
			$('#successMsg').css('display','block');
			$('#mainContent').css('display','none');
			 window.setTimeout(window.location.reload(), 20000);
           // console.log("Closing");
			
        }
function closeModal(){
       
	   $('#pageMsgModal').modal('hide');
      page3=true;
	   var name = document.getElementById("name").value;
       var email = document.getElementById("email").value;
       var mobile = document.getElementById("number").value;
       var company = document.getElementById("company").value;
		   $('#userInfo').css('display','block');
	       $('#overlay').css('display','block');
	       $('#formContent').css('display','none');
		   $('#countdownExample').css('display','block');
		   var timer = new Timer();
            timer.start({countdown: true, startValues: {seconds: (timeout/1000)}});
              $('#countdownExample .values').html(timer.getTimeValues().toString());
              timer.addEventListener('secondsUpdated', function (e) {
               $('#countdownExample .values').html(timer.getTimeValues().toString());
              });
            timer.addEventListener('targetAchieved', function (e) {
            $('#countdownExample .values').html('NICE TO SEE YOU !!');
              });
          
           var msg = {
            'type': 'INFO',
            'name': name,
            'mail' : email,
            'mobile' : mobile,
            'company' : company
             };
       console.log("Submiting info");
       socket.send(JSON.stringify(msg));
}
