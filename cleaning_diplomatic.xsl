<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:tei="http://www.tei-c.org/ns/1.0"
                version="3.0">

  <xsl:output method="xml" indent="yes"/>

  <!-- Identity template -->
  <xsl:template match="/ | @* | node()">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- DIPLOMATIC: Remove regularizations, expansions, additions, corrections -->
  <xsl:template match="tei:expan[not(@ana='retain')] | tei:reg[not(@ana='retain')] | tei:add[not(@ana='retain')] | tei:corr[not(@ana='retain')]" />
  <xsl:template match="*[@ana='ignore']" />
  
  <!-- DIPLOMATIC: Keep originals and errors (sic), remove critical apparatus -->
  <!-- Keep tei:orig, tei:sic, tei:del, tei:surplus, tei:supplied in diplomatic -->

</xsl:stylesheet>
