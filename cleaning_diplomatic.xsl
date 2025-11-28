<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:tei="http://www.tei-c.org/ns/1.0"
                version="3.0">

  <xsl:output method="xml" indent="no"/>

  <!-- Identity -->
  <xsl:template match="/ | @* | node()">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- DIPLOMATIC: Remove regularisations, expansions, additions, corrections -->
  <xsl:template match="tei:expan[not(@ana='retain')]
                      | tei:reg[not(@ana='retain')]
                      | tei:corr[not(@ana='retain')]
                      | tei:add[not(@ana='retain')]
                      | tei:supplied[not(@ana='retain')]" />

  <!-- Remove elements explicitly marked ignore -->
  <xsl:template match="*[@ana='ignore']"/>

</xsl:stylesheet>
