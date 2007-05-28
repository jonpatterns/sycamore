function createMarker(point, index, text) {
        var letter = String.fromCharCode("A".charCodeAt(0) + index);
        var icon = new GIcon(baseIcon);
        icon.image = "http://www.google.com/mapfiles/marker" + letter + ".png";
        var marker = new GMarker(point, icon);

        GEvent.addListener(marker, "click", function() {
                marker.openInfoWindowHtml(text);
                });
        return marker;
}

function createArrow(point,text) {
    icon = new GIcon(pointIcon);
    icon.image = "http://www.google.com/mapfiles/arrow.png";
    var marker = new GMarker(point,icon);
    GEvent.addListener(marker,"click", function() {
            marker.openInfoWindowHtml(text);
    });
    return marker;
}

function loadMap() {
    loadedMap = false;
    if (loadedMap) return; 
    if (map_url && !loadedMapAtLeastOnce) {
        loadedMapAtLeastOnce = true;
        /* When we're not in the actual iframe */
        var ifr = document.createElement("iframe");
        ifr.src = map_url; 
        ifr.frameborder = 0; 
        ifr.scrolling = "no";
        ifr.marginwidth = 0;
        ifr.width = 449;
        ifr.height = 299;
        ifr.style.border = "none";
        document.getElementById("map").appendChild(ifr);
    }
    else /* We're in the iframe! */ {
        initLoad();
    }
}

var loadedMap;
var loadedMapAtLeastOnce = false;
var mapon;
var baseIcon;
var pointIcon;
var marker;
var icon;
var map_url = '';

function initLoad()
{
    
    mapon = false;
    baseIcon = new GIcon();
    baseIcon.shadow = "http://www.google.com/mapfiles/shadow50.png";
    baseIcon.iconSize = new GSize(20, 34);
    baseIcon.shadowSize = new GSize(37, 34);
    baseIcon.iconAnchor = new GPoint(9, 34);
    baseIcon.infoWindowAnchor = new GPoint(9, 2);
    baseIcon.infoShadowAnchor = new GPoint(18, 25);

    pointIcon = new GIcon();
    pointIcon.shadow = "http://www.google.com/mapfiles/arrowshadow.png";
    pointIcon.iconSize = new GSize(39, 34);
    pointIcon.shadowSize = new GSize(37, 34);
    pointIcon.iconAnchor = new GPoint(9, 34);
    pointIcon.infoWindowAnchor = new GPoint(9, 2);
    pointIcon.infoShadowAnchor = new GPoint(18, 25);

    doLoad();
    }
