<xsl:stylesheet version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="#all">

  <!-- Identity -->
  <xsl:mode on-no-match="shallow-copy"/>

  <!-- Parameter -->
  <xsl:param name="div-id"/>

  <!-- Root template -->
  <xsl:template match="/">
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <xsl:copy-of select="//tei:teiHeader"/>

      <text>
        <body>

          <!-- Copy nearest preceding pb -->
          <xsl:copy-of
            select="//tei:div[@xml:id=$div-id]
                      /preceding::tei:pb[1]"
          />

          <!-- Copy the div itself -->
          <xsl:copy-of
            select="//tei:div[@xml:id=$div-id]"
          />

        </body>
      </text>
    </TEI>
  </xsl:template>

</xsl:stylesheet>
