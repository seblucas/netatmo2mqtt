# netatmo2mqtt

Get the measures from your NetAtmo thermostat and send it to your MQTT broker

# Why yet another tool around NetAtmo API

I tried many other open source tools on github but I did not find a perfect fit for me.

The main reason is security : most of the tools I reviewed are still asking for `client_id`, `client_secret` (perfectly normal) but also for your username / password and that's not acceptable for me. It's also forbidden by [NetAtmo guidelines](https://dev.netatmo.com/resources/technical/guides/developerguidelines).

So I build mine :(.

# Usage

## Prerequisite

# Limits

 * This program only handles Thermostat for now (PR welcome for other sensors)
 * Won't work if you have more than one thermostat (again PR welcome)

# License

This program is licenced with GNU GENERAL PUBLIC LICENSE version 3 by Free Software Foundation, Inc.
 
