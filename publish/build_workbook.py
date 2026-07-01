"""Assemble a Tableau .twbx from the Olist order-level .hyper extract by
generating the .twb XML (Tableau has no headless authoring API).

"Olist Marketplace Overview" — a CEO/finance executive dashboard, Lynk-branded
(purple #6749F4 on white):
  - purple title banner
  - 4 KPI stat tiles : Total GMV (R$) / Orders / Customers / Avg Review
  - line : monthly GMV (R$) trend
  - bar  : GMV by customer state (sorted)
  - bar  : late-delivery rate by shipping-distance band (the logistics insight)
  - bar  : orders by Brazilian season
All panels aggregate the single embedded order-level Hyper table.

Usage:  python publish/build_workbook.py <input.hyper> <output.twbx>
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

HYPER_REL = "Data/olist_orders.hyper"
DS = "federated.olist"
HYPERCONN = "hyper.olist"

ACCENT = "#6749F4"
INK = "#171717"
LABEL = "#78737D"
BANNERTXT = "#FFFFFF"

BLANK_TITLE = "<layout-options><title><formatted-text><run>&#160;</run></formatted-text></title></layout-options>"

LATE_RATE = "<column caption='Late-Delivery Rate' datatype='real' default-format='p0%' name='[LATE_RATE]' role='measure' type='quantitative'><calculation class='tableau' formula='AVG([IS_LATE])' /></column>"


def kpi(name: str, value_ref: str, deps: str, fontsize: int = 26) -> str:
    return f"""    <worksheet name='{name}'>
      {BLANK_TITLE}
      <table>
        <view>
          <datasources>
            <datasource caption='Olist Orders (dbt)' name='{DS}' />
          </datasources>
          <datasource-dependencies datasource='{DS}'>
            {deps}
          </datasource-dependencies>
        </view>
        <style>
          <style-rule element='mark'>
            <format attr='mark-color' value='{ACCENT}' />
            <format attr='font-size' value='{fontsize}' />
          </style-rule>
        </style>
        <panes>
          <pane>
            <view><breakdown value='auto' /></view>
            <mark class='Text' />
            <encodings>
              <text column='[{DS}].{value_ref}' />
            </encodings>
          </pane>
        </panes>
        <rows></rows>
        <cols></cols>
      </table>
    </worksheet>
"""


def label_zone(zid: int, x: int, w: int, text: str) -> str:
    return f"""          <zone h='1800' id='{zid}' type-v2='text' w='{w}' x='{x}' y='4000'>
            <formatted-text><run bold='true' fontcolor='{LABEL}' fontsize='9'>{text}</run></formatted-text>
            <zone-style>
              <format attr='background-color' value='#FFFFFF' />
              <format attr='border-style' value='none' />
              <format attr='margin' value='4' />
              <format attr='padding-top' value='6' />
              <format attr='padding-left' value='10' />
            </zone-style>
          </zone>
"""


def number_zone(zid: int, x: int, w: int, name: str) -> str:
    return f"""          <zone h='7000' id='{zid}' name='{name}' w='{w}' x='{x}' y='5800'>
            <zone-style>
              <format attr='border-color' value='#E5E5E5' />
              <format attr='border-style' value='solid' />
              <format attr='border-width' value='1' />
              <format attr='margin' value='4' />
            </zone-style>
          </zone>
"""


def chart_zone(zid: int, name: str, y: int, h: int) -> str:
    return f"""          <zone h='{h}' id='{zid}' name='{name}' w='100000' x='0' y='{y}'>
            <zone-style>
              <format attr='border-style' value='none' />
              <format attr='border-width' value='0' />
              <format attr='margin' value='6' />
            </zone-style>
          </zone>
"""


KPIS = (
    kpi("Total GMV", "[sum:GMV_BRL:qk]",
        "<column datatype='real' default-format='&quot;R$&quot;#,##0' name='[GMV_BRL]' caption='GMV (BRL)' role='measure' type='quantitative' />\n"
        "            <column-instance column='[GMV_BRL]' derivation='Sum' name='[sum:GMV_BRL:qk]' pivot='key' type='quantitative' />")
    + kpi("Orders", "[ctd:ORDER_ID:qk]",
        "<column datatype='string' name='[ORDER_ID]' role='dimension' type='nominal' />\n"
        "            <column-instance column='[ORDER_ID]' derivation='CountD' name='[ctd:ORDER_ID:qk]' pivot='key' type='quantitative' />")
    + kpi("Customers", "[ctd:CUSTOMER_ID:qk]",
        "<column datatype='string' name='[CUSTOMER_ID]' role='dimension' type='nominal' />\n"
        "            <column-instance column='[CUSTOMER_ID]' derivation='CountD' name='[ctd:CUSTOMER_ID:qk]' pivot='key' type='quantitative' />")
    + kpi("Avg Review", "[avg:REVIEW_SCORE:qk]",
        "<column datatype='real' default-format='0.00' name='[REVIEW_SCORE]' caption='Review Score' role='measure' type='quantitative' />\n"
        "            <column-instance column='[REVIEW_SCORE]' derivation='Avg' name='[avg:REVIEW_SCORE:qk]' pivot='key' type='quantitative' />")
)

TWB = f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='2023.3' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
    <datasource caption='Olist Orders (dbt)' inline='true' name='{DS}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='olist_orders' name='{HYPERCONN}'>
            <connection class='hyper' dbname='{HYPER_REL}' default-settings='yes' schema='Extract' />
          </named-connection>
        </named-connections>
        <relation connection='{HYPERCONN}' name='Extract' table='[Extract].[Extract]' type='table' />
        <cols>
          <map key='[ORDER_ID]' value='[Extract].[ORDER_ID]' />
          <map key='[CUSTOMER_ID]' value='[Extract].[CUSTOMER_ID]' />
          <map key='[ORDER_MONTH]' value='[Extract].[ORDER_MONTH]' />
          <map key='[ORDER_YEAR]' value='[Extract].[ORDER_YEAR]' />
          <map key='[GMV_BRL]' value='[Extract].[GMV_BRL]' />
          <map key='[PRIMARY_CATEGORY]' value='[Extract].[PRIMARY_CATEGORY]' />
          <map key='[CUSTOMER_STATE]' value='[Extract].[CUSTOMER_STATE]' />
          <map key='[ORDER_STATUS]' value='[Extract].[ORDER_STATUS]' />
          <map key='[IS_LATE]' value='[Extract].[IS_LATE]' />
          <map key='[DELIVERY_DAYS]' value='[Extract].[DELIVERY_DAYS]' />
          <map key='[REVIEW_SCORE]' value='[Extract].[REVIEW_SCORE]' />
          <map key='[DISTANCE_KM]' value='[Extract].[DISTANCE_KM]' />
          <map key='[DISTANCE_BUCKET]' value='[Extract].[DISTANCE_BUCKET]' />
          <map key='[DISTANCE_ORDER]' value='[Extract].[DISTANCE_ORDER]' />
          <map key='[BRAZILIAN_SEASON]' value='[Extract].[BRAZILIAN_SEASON]' />
        </cols>
      </connection>
      <column datatype='string' name='[ORDER_ID]' role='dimension' type='nominal' />
      <column datatype='string' name='[CUSTOMER_ID]' role='dimension' type='nominal' />
      <column datatype='date' name='[ORDER_MONTH]' caption='Order Month' role='dimension' type='ordinal' />
      <column datatype='integer' name='[ORDER_YEAR]' caption='Year' role='dimension' type='ordinal' />
      <column datatype='real' default-format='&quot;R$&quot;#,##0' name='[GMV_BRL]' caption='GMV (BRL)' role='measure' type='quantitative' />
      <column datatype='string' name='[PRIMARY_CATEGORY]' caption='Category' role='dimension' type='nominal' />
      <column datatype='string' name='[CUSTOMER_STATE]' caption='Customer State' role='dimension' type='nominal' />
      <column datatype='string' name='[ORDER_STATUS]' caption='Order Status' role='dimension' type='nominal' />
      <column datatype='integer' name='[IS_LATE]' role='measure' type='quantitative' />
      <column datatype='real' name='[DELIVERY_DAYS]' caption='Delivery Days' role='measure' type='quantitative' />
      <column datatype='real' default-format='0.00' name='[REVIEW_SCORE]' caption='Review Score' role='measure' type='quantitative' />
      <column datatype='real' name='[DISTANCE_KM]' caption='Distance (km)' role='measure' type='quantitative' />
      <column datatype='string' name='[DISTANCE_BUCKET]' caption='Distance Band' role='dimension' type='nominal' />
      <column datatype='integer' name='[DISTANCE_ORDER]' role='measure' type='quantitative' />
      <column datatype='string' name='[BRAZILIAN_SEASON]' caption='Season' role='dimension' type='nominal' />
      {LATE_RATE}
    </datasource>
  </datasources>
  <worksheets>
{KPIS}    <worksheet name='GMV by Month'>
      <table>
        <view>
          <datasources>
            <datasource caption='Olist Orders (dbt)' name='{DS}' />
          </datasources>
          <datasource-dependencies datasource='{DS}'>
            <column datatype='date' name='[ORDER_MONTH]' caption='Order Month' role='dimension' type='ordinal' />
            <column-instance column='[ORDER_MONTH]' derivation='None' name='[none:ORDER_MONTH:qk]' pivot='key' type='quantitative' />
            <column datatype='real' default-format='&quot;R$&quot;#,##0' name='[GMV_BRL]' caption='GMV (BRL)' role='measure' type='quantitative' />
            <column-instance column='[GMV_BRL]' derivation='Sum' name='[sum:GMV_BRL:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
        </view>
        <style>
          <style-rule element='mark'><format attr='mark-color' value='{ACCENT}' /></style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view><breakdown value='auto' /></view>
            <mark class='Line' />
          </pane>
        </panes>
        <rows>[{DS}].[sum:GMV_BRL:qk]</rows>
        <cols>[{DS}].[none:ORDER_MONTH:qk]</cols>
      </table>
    </worksheet>
    <worksheet name='GMV by Customer State'>
      <table>
        <view>
          <datasources>
            <datasource caption='Olist Orders (dbt)' name='{DS}' />
          </datasources>
          <datasource-dependencies datasource='{DS}'>
            <column datatype='string' name='[CUSTOMER_STATE]' caption='Customer State' role='dimension' type='nominal' />
            <column-instance column='[CUSTOMER_STATE]' derivation='None' name='[none:CUSTOMER_STATE:nk]' pivot='key' type='nominal' />
            <column datatype='real' default-format='&quot;R$&quot;#,##0' name='[GMV_BRL]' caption='GMV (BRL)' role='measure' type='quantitative' />
            <column-instance column='[GMV_BRL]' derivation='Sum' name='[sum:GMV_BRL:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
          <sort class='computed' column='[{DS}].[none:CUSTOMER_STATE:nk]' direction='DESC' using='[{DS}].[sum:GMV_BRL:qk]' />
        </view>
        <style>
          <style-rule element='mark'><format attr='mark-color' value='{ACCENT}' /></style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view><breakdown value='auto' /></view>
            <mark class='Bar' />
          </pane>
        </panes>
        <rows>[{DS}].[none:CUSTOMER_STATE:nk]</rows>
        <cols>[{DS}].[sum:GMV_BRL:qk]</cols>
      </table>
    </worksheet>
    <worksheet name='Late Rate by Distance'>
      <table>
        <view>
          <datasources>
            <datasource caption='Olist Orders (dbt)' name='{DS}' />
          </datasources>
          <datasource-dependencies datasource='{DS}'>
            <column datatype='string' name='[DISTANCE_BUCKET]' caption='Distance Band' role='dimension' type='nominal' />
            <column-instance column='[DISTANCE_BUCKET]' derivation='None' name='[none:DISTANCE_BUCKET:nk]' pivot='key' type='nominal' />
            <column datatype='integer' name='[DISTANCE_ORDER]' role='measure' type='quantitative' />
            <column-instance column='[DISTANCE_ORDER]' derivation='Avg' name='[avg:DISTANCE_ORDER:qk]' pivot='key' type='quantitative' />
            <column datatype='integer' name='[IS_LATE]' role='measure' type='quantitative' />
            {LATE_RATE}
          </datasource-dependencies>
          <sort class='computed' column='[{DS}].[none:DISTANCE_BUCKET:nk]' direction='ASC' using='[{DS}].[avg:DISTANCE_ORDER:qk]' />
          <filter class='categorical' column='[{DS}].[none:DISTANCE_BUCKET:nk]'>
            <groupfilter function='union' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enter'>
              <groupfilter function='member' level='[none:DISTANCE_BUCKET:nk]' member='&quot;0-50km&quot;' />
              <groupfilter function='member' level='[none:DISTANCE_BUCKET:nk]' member='&quot;50-200km&quot;' />
              <groupfilter function='member' level='[none:DISTANCE_BUCKET:nk]' member='&quot;200-500km&quot;' />
              <groupfilter function='member' level='[none:DISTANCE_BUCKET:nk]' member='&quot;500-1000km&quot;' />
              <groupfilter function='member' level='[none:DISTANCE_BUCKET:nk]' member='&quot;1000km+&quot;' />
            </groupfilter>
          </filter>
        </view>
        <style>
          <style-rule element='mark'><format attr='mark-color' value='{INK}' /></style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view><breakdown value='auto' /></view>
            <mark class='Bar' />
          </pane>
        </panes>
        <rows>[{DS}].[none:DISTANCE_BUCKET:nk]</rows>
        <cols>[{DS}].[LATE_RATE]</cols>
      </table>
    </worksheet>
    <worksheet name='Orders by Season'>
      <table>
        <view>
          <datasources>
            <datasource caption='Olist Orders (dbt)' name='{DS}' />
          </datasources>
          <datasource-dependencies datasource='{DS}'>
            <column datatype='string' name='[BRAZILIAN_SEASON]' caption='Season' role='dimension' type='nominal' />
            <column-instance column='[BRAZILIAN_SEASON]' derivation='None' name='[none:BRAZILIAN_SEASON:nk]' pivot='key' type='nominal' />
            <column datatype='string' name='[ORDER_ID]' role='dimension' type='nominal' />
            <column-instance column='[ORDER_ID]' derivation='CountD' name='[ctd:ORDER_ID:qk]' pivot='key' type='quantitative' />
          </datasource-dependencies>
          <sort class='computed' column='[{DS}].[none:BRAZILIAN_SEASON:nk]' direction='DESC' using='[{DS}].[ctd:ORDER_ID:qk]' />
        </view>
        <style>
          <style-rule element='mark'><format attr='mark-color' value='{ACCENT}' /></style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view><breakdown value='auto' /></view>
            <mark class='Bar' />
          </pane>
        </panes>
        <rows>[{DS}].[none:BRAZILIAN_SEASON:nk]</rows>
        <cols>[{DS}].[ctd:ORDER_ID:qk]</cols>
      </table>
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name='Olist Marketplace Overview'>
      <style />
      <size maxheight='2200' maxwidth='1700' minheight='2200' minwidth='1700' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
          <zone h='4000' id='10' type-v2='text' w='100000' x='0' y='0'>
            <formatted-text><run bold='true' fontcolor='{BANNERTXT}' fontsize='22'>Olist Marketplace Overview</run></formatted-text>
            <zone-style>
              <format attr='background-color' value='{ACCENT}' />
              <format attr='background-opacity' value='1.0' />
              <format attr='border-style' value='none' />
              <format attr='border-width' value='0' />
              <format attr='margin' value='0' />
              <format attr='padding-top' value='10' />
              <format attr='padding-left' value='16' />
            </zone-style>
          </zone>
{label_zone(20, 0, 25000, "TOTAL GMV (R$)")}{label_zone(21, 25000, 25000, "ORDERS")}{label_zone(22, 50000, 25000, "CUSTOMERS")}{label_zone(23, 75000, 25000, "AVG REVIEW (1-5)")}{number_zone(11, 0, 25000, "Total GMV")}{number_zone(12, 25000, 25000, "Orders")}{number_zone(13, 50000, 25000, "Customers")}{number_zone(14, 75000, 25000, "Avg Review")}{chart_zone(15, "GMV by Month", 13000, 18000)}{chart_zone(16, "GMV by Customer State", 31000, 34000)}{chart_zone(17, "Late Rate by Distance", 65000, 17000)}{chart_zone(18, "Orders by Season", 82000, 18000)}        </zone>
      </zones>
    </dashboard>
  </dashboards>
  <windows source-height='30'>
    <window class='worksheet' name='Total GMV' />
    <window class='worksheet' name='Orders' />
    <window class='worksheet' name='Customers' />
    <window class='worksheet' name='Avg Review' />
    <window class='worksheet' name='GMV by Month' />
    <window class='worksheet' name='GMV by Customer State' />
    <window class='worksheet' name='Late Rate by Distance' />
    <window class='worksheet' name='Orders by Season' />
    <window class='dashboard' name='Olist Marketplace Overview'>
      <viewpoints>
        <viewpoint name='Total GMV' />
        <viewpoint name='Orders' />
        <viewpoint name='Customers' />
        <viewpoint name='Avg Review' />
        <viewpoint name='GMV by Month' />
        <viewpoint name='GMV by Customer State' />
        <viewpoint name='Late Rate by Distance' />
        <viewpoint name='Orders by Season' />
      </viewpoints>
      <active id='-1' />
    </window>
  </windows>
</workbook>
"""


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python publish/build_workbook.py <input.hyper> <output.twbx>")
    hyper_in = Path(sys.argv[1])
    twbx_out = Path(sys.argv[2])
    if not hyper_in.exists():
        sys.exit(f"Hyper not found: {hyper_in}")
    twbx_out.parent.mkdir(parents=True, exist_ok=True)

    import xml.dom.minidom as minidom
    minidom.parseString(TWB)  # fail fast on malformed XML

    if twbx_out.exists():
        twbx_out.unlink()
    with zipfile.ZipFile(twbx_out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("olist_overview.twb", TWB)
        z.write(hyper_in, HYPER_REL)
    print(f"Packaged {twbx_out} ({twbx_out.stat().st_size} bytes)")
    with zipfile.ZipFile(twbx_out) as z:
        print("Contents:", z.namelist())


if __name__ == "__main__":
    main()
