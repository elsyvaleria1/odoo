/** @odoo-module native */
function initialize_map() {
    "use strict";

    const map = new google.maps.Map(document.getElementById("odoo-google-map"), {
        zoom: 1,
        center: { lat: 0.0, lng: 0.0 },
        mapTypeId: google.maps.MapTypeId.ROADMAP,
        gestureHandling: "greedy",
    });

    const Geocoder = new google.maps.Geocoder();

    const infoWindow = new google.maps.InfoWindow();
    const partners = new google.maps.MarkerImage(
        "/website_google_map/static/src/img/partners.png",
        new google.maps.Size(25, 25),
    );
    const partner_url = document.body.getAttribute("data-partner-url") || "";
    const markers = [];
    const options = {
        imagePath: "/website_google_map/static/src/lib/images/m",
    };

    google.maps.event.addListener(map, "click", function () {
        infoWindow.close();
    });

    const onMarkerClick = function () {
        const marker = this;
        const p = marker.partner;
        infoWindow.setContent(
            '<div class="marker">' +
                (partner_url.length
                    ? '<a target="_top" href="' +
                      partner_url +
                      p.id +
                      '"><b>' +
                      p.name +
                      "</b></a>"
                    : "<b>" + p.name + "</b>") +
                (p.type ? "  <b>" + p.type + "</b>" : "") +
                "  <pre>" +
                p.address +
                "</pre>" +
                "</div>",
        );
        infoWindow.open(map, marker);
    };

    const set_marker = function (partner) {
        return new Promise((resolve, reject) => {
            if (!partner.latitude && !partner.longitude) {
                Geocoder.geocode(
                    { address: partner.address },
                    function (results, status) {
                        if (status === google.maps.GeocoderStatus.OK) {
                            const location = results[0].geometry.location;
                            partner.latitude = location.ob;
                            partner.longitude = location.pb;
                            const marker = new google.maps.Marker({
                                partner: partner,
                                map: map,
                                icon: partners,
                                position: location,
                            });
                            google.maps.event.addListener(
                                marker,
                                "click",
                                onMarkerClick,
                            );
                            markers.push(marker);
                            resolve();
                        } else {
                            console.warn(
                                "Geocode was not successful for the following reason: " +
                                    status,
                            );
                            reject("Geocode failed: " + status);
                        }
                    },
                );
            } else {
                const latLng = new google.maps.LatLng(
                    partner.latitude,
                    partner.longitude,
                );
                const marker = new google.maps.Marker({
                    partner: partner,
                    icon: partners,
                    map: map,
                    position: latLng,
                });
                google.maps.event.addListener(marker, "click", onMarkerClick);
                markers.push(marker);
                resolve();
            }
        });
    };

    /* eslint-disable no-undef */
    async function initializeMarkers(odooPartnerData) {
        if (odooPartnerData) {
            const markerPromises = [];
            for (let i = 0; i < odoo_partner_data.counter; i++) {
                const prom = set_marker(odoo_partner_data.partners[i]).catch((error) =>
                    console.error(error),
                );
                markerPromises.push(prom);
            }
            await Promise.all(markerPromises);
            new MarkerClusterer(map, markers, options);

            const bounds = new google.maps.LatLngBounds();
            markers.forEach((n) => bounds.extend(n.position));
            map.setCenter(bounds.getCenter());
            map.fitBounds(bounds);
            map.setZoom(map.getZoom() - 1);
        }
    }

    initializeMarkers(odoo_partner_data);
    /* eslint-enable no-undef */
}

google.maps.event.addDomListener(window, "load", initialize_map);
