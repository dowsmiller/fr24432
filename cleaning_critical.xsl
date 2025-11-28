<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:tei="http://www.tei-c.org/ns/1.0"
                version="3.0">

  <xsl:output method="xml" indent="no"/>

  <!-- Identity -->
  <xsl:template match="@* | node()">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- CRITICAL: Remove originals, errors, deletions, surplus, supplied -->
  <xsl:template match="tei:abbr[not(@ana='retain')] 
                      | tei:orig[not(@ana='retain')]
                      | tei:sic[not(@ana='retain')]
                      | tei:del[not(@ana='retain')]
                      | tei:surplus[not(@ana='retain')]"/>

  <!-- Remove elements explicitly marked ignore -->
  <xsl:template match="*[@ana='ignore']"/>

</xsl:stylesheet>
